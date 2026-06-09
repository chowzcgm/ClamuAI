<?php
require_once __DIR__ . '/../includes/functions.php';

$jobId = $_GET['job_id'] ?? '';
$type = $_GET['type'] ?? 'original'; // original or processed
$jobId = preg_replace('/[^a-f0-9]/', '', $jobId);

if (!$jobId) {
    sendJson(['error' => '缺少 job_id'], 400);
}

if ($type === 'processed') {
    $found = glob(OUTPUT_DIR . '/' . $jobId . '_processed.*');
} else {
    $found = glob(UPLOAD_DIR . '/' . $jobId . '.*');
}

if (empty($found)) {
    sendJson(['error' => '文件不存在'], 404);
}

$filepath = $found[0];

$result = runPython('audio_utils.py', [
    'action' => 'spectrogram_json',
    'input' => $filepath,
    'job_id' => $jobId
]);

$data = json_decode($result['output'], true);

header('Content-Type: image/png');
if ($data && isset($data['spectrogram_image'])) {
    echo base64_decode($data['spectrogram_image']);
} else {
    // Generate a blank spectrogram
    $img = imagecreatetruecolor(800, 400);
    $bg = imagecolorallocate($img, 20, 20, 30);
    imagefill($img, 0, 0, $bg);
    imagepng($img);
    imagedestroy($img);
}
