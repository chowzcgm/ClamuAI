<?php
require_once __DIR__ . '/../includes/functions.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sendJson(['error' => '仅支持 POST 请求'], 405);
}

$input = json_decode(file_get_contents('php://input'), true);
if (!$input || empty($input['job_id']) || empty($input['modules'])) {
    sendJson(['error' => '缺少必要参数: job_id, modules'], 400);
}

$jobId = preg_replace('/[^a-f0-9]/', '', $input['job_id']);
$modules = $input['modules'];
$intensity = floatval($input['intensity'] ?? 0.6);
$intensity = max(0.1, min(1.0, $intensity));

// Find the uploaded file
$found = glob(UPLOAD_DIR . '/' . $jobId . '.*');
if (empty($found)) {
    sendJson(['error' => '找不到上传的文件，请重新上传'], 404);
}

$inputFile = $found[0];
$ext = getFileExtension($inputFile);
$outputFile = OUTPUT_DIR . '/' . $jobId . '_processed.' . $ext;

writeJobStatus($jobId, [
    'status' => 'processing',
    'total' => count($modules),
    'current' => 0,
    'current_module' => '',
    'modules' => $modules,
    'log' => []
]);

// Build pipeline
$pipeline = [];
foreach ($modules as $module) {
    if (!isset(MODULES[$module])) continue;
    $pipeline[] = [
        'script' => $module . '.py',
        'name' => MODULES[$module]
    ];
}

if (empty($pipeline)) {
    sendJson(['error' => '没有选择有效的处理模块'], 400);
}

$currentFile = $inputFile;
$totalSteps = count($pipeline);
$stepNum = 0;

foreach ($pipeline as $step) {
    $stepNum++;
    $stepOutputFile = TEMP_DIR . '/' . $jobId . '_step' . $stepNum . '.wav';

    $result = runPython($step['script'], [
        'input' => $currentFile,
        'output' => $stepOutputFile,
        'intensity' => $intensity,
        'job_id' => $jobId,
        'step' => $stepNum
    ]);

    $status = readJobStatus($jobId);
    $log = $status['log'] ?? [];

    if ($result['success']) {
        $log[] = "[{$stepNum}/{$totalSteps}] {$step['name']} - 完成";
        $currentFile = $stepOutputFile;
    } else {
        $log[] = "[{$stepNum}/{$totalSteps}] {$step['name']} - 失败: {$result['output']}";
        writeJobStatus($jobId, [
            'status' => 'failed',
            'total' => $totalSteps,
            'current' => $stepNum,
            'current_module' => $step['name'],
            'log' => $log,
            'error' => $result['output']
        ]);
        sendJson(['error' => "{$step['name']} 处理失败", 'log' => $log, 'job_id' => $jobId], 500);
    }

    writeJobStatus($jobId, [
        'status' => 'processing',
        'total' => $totalSteps,
        'current' => $stepNum,
        'current_module' => $step['name'],
        'log' => $log
    ]);
}

// Move final output
rename($currentFile, $outputFile);

writeJobStatus($jobId, [
    'status' => 'completed',
    'total' => $totalSteps,
    'current' => $totalSteps,
    'current_module' => '',
    'log' => $log,
    'output_file' => basename($outputFile),
    'output_url' => 'index.php?action=download&file=' . urlencode(basename($outputFile))
]);

// Cleanup intermediate temp files
cleanTempFiles($jobId);

sendJson([
    'job_id' => $jobId,
    'status' => 'completed',
    'output_file' => basename($outputFile),
    'output_url' => 'index.php?action=download&file=' . urlencode(basename($outputFile)),
    'log' => $log
]);
