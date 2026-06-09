<?php
require_once __DIR__ . '/../includes/functions.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sendJson(['error' => '仅支持 POST 请求'], 405);
}

$input = json_decode(file_get_contents('php://input'), true);
$jobId = $input['job_id'] ?? '';
$jobId = preg_replace('/[^a-f0-9]/', '', $jobId);

if (!$jobId) {
    sendJson(['error' => '缺少 job_id'], 400);
}

$found = glob(OUTPUT_DIR . '/' . $jobId . '_processed.*');
if (empty($found)) {
    sendJson(['error' => '未找到处理后的文件，请先完成处理'], 404);
}

$filepath = $found[0];
$result = runPython('audio_utils.py', [
    'action' => 'analyze',
    'input' => $filepath
]);

$analysis = json_decode($result['output'], true);
sendJson([
    'job_id' => $jobId,
    'file' => basename($filepath),
    'analysis' => $analysis
]);
