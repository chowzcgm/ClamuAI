<?php
require_once __DIR__ . '/../includes/functions.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sendJson(['error' => '仅支持 POST 请求'], 405);
}

if (!isset($_FILES['audio'])) {
    sendJson(['error' => '未收到文件'], 400);
}

$file = $_FILES['audio'];
$error = validateAudioFile($file);
if ($error) {
    sendJson(['error' => $error], 400);
}

$jobId = generateId();
$ext = getFileExtension($file['name']);
$filename = $jobId . '.' . $ext;
$dest = UPLOAD_DIR . '/' . $filename;

if (!move_uploaded_file($file['tmp_name'], $dest)) {
    sendJson(['error' => '文件保存失败'], 500);
}

$info = getAudioInfo($dest);

sendJson([
    'job_id' => $jobId,
    'filename' => $file['name'],
    'size' => $file['size'],
    'duration' => $info['duration'] ?? 0,
    'sample_rate' => $info['sample_rate'] ?? 0,
    'channels' => $info['channels'] ?? 0,
    'ext' => $ext
]);
