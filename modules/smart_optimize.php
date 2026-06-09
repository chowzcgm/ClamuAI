<?php
require_once __DIR__ . '/../includes/functions.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sendJson(['error' => '仅支持 POST 请求'], 405);
}

$input = json_decode(file_get_contents('php://input'), true);
if (!$input || empty($input['job_id'])) {
    sendJson(['error' => '缺少必要参数: job_id'], 400);
}

$jobId = preg_replace('/[^a-f0-9]/', '', $input['job_id']);
$intensity = floatval($input['intensity'] ?? 0.6);

$found = glob(UPLOAD_DIR . '/' . $jobId . '.*');
if (empty($found)) {
    sendJson(['error' => '找不到上传的文件，请重新上传'], 404);
}

$inputFile = $found[0];
$ext = getFileExtension($inputFile);
$outputFile = OUTPUT_DIR . '/' . $jobId . '_processed.' . $ext;

writeJobStatus($jobId, [
    'status' => 'processing',
    'total' => 1,
    'current' => 0,
    'current_module' => 'MMM引擎处理中...',
    'log' => ['启动 MMM 引擎处理...']
]);

// Use mmm_wrapper.py - calls mmm's preserving sanitizer directly, bypassing Rich/CLI
$log = ['启动 MMM 引擎处理...'];
$log[] = '强度: ' . round($intensity, 2);

$result = runPython('mmm_wrapper.py', [
    'input' => $inputFile,
    'output' => $outputFile,
    'intensity' => $intensity
]);

$threatsFound = 0;
$patternsSuppressed = 0;
$qualityLoss = 0;

if ($result['success']) {
    $wrapperOutput = json_decode($result['output'], true);
    if ($wrapperOutput && isset($wrapperOutput['status']) && $wrapperOutput['status'] === 'ok') {
        // Success
    }
}

// Check output file existence as success indicator
if (file_exists($outputFile) && filesize($outputFile) > 1000) {
    $log[] = "MMM 处理完成";

    // Run quality check: compare original vs processed
    $log[] = "运行质量分析...";
    $qualityResult = runPython('quality_check.py', [
        'original' => $inputFile,
        'processed' => $outputFile
    ]);
    $quality = null;
    if ($qualityResult['success']) {
        $quality = json_decode($qualityResult['output'], true);
        if ($quality && !isset($quality['error'])) {
            $log[] = "音乐保留度: " . round($quality['overall_music_preservation'] ?? 0, 1) . "%";
            $log[] = "水印破坏度: " . round($quality['watermark_disruption'] ?? 0, 1) . "%";
            $log[] = "AI痕迹分数变化: " . ($quality['ai_score']['delta'] ?? 'N/A');
        }
    }

    writeJobStatus($jobId, [
        'status' => 'completed',
        'total' => 1,
        'current' => 1,
        'current_module' => '',
        'log' => $log,
        'output_file' => basename($outputFile),
        'output_url' => 'index.php?action=download&file=' . urlencode(basename($outputFile)),
        'threats_found' => $threatsFound,
        'patterns_suppressed' => $patternsSuppressed,
        'quality_loss' => $qualityLoss,
        'quality' => $quality
    ]);

    sendJson([
        'job_id' => $jobId,
        'status' => 'completed',
        'output_file' => basename($outputFile),
        'output_url' => 'index.php?action=download&file=' . urlencode(basename($outputFile)),
        'threats_found' => $threatsFound,
        'patterns_suppressed' => $patternsSuppressed,
        'quality_loss' => $qualityLoss,
        'quality' => $quality,
        'log' => $log
    ]);
} else {
    $errorMsg = implode("\n", array_slice($output, -10));
    $log[] = '失败: ' . $errorMsg;
    writeJobStatus($jobId, [
        'status' => 'failed',
        'log' => $log,
        'error' => $errorMsg
    ]);
    sendJson(['error' => 'MMM 处理失败', 'log' => $log, 'details' => $errorMsg], 500);
}
