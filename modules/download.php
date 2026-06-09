<?php
require_once __DIR__ . '/../includes/functions.php';

$file = $_GET['file'] ?? '';
$file = basename($file); // Prevent directory traversal

$path = OUTPUT_DIR . '/' . $file;
if (!file_exists($path)) {
    http_response_code(404);
    die('文件不存在');
}

$mime = mime_content_type($path);
if (!$mime) {
    $mime = 'audio/wav';
}

header('Content-Type: ' . $mime);
header('Content-Length: ' . filesize($path));
header('Content-Disposition: attachment; filename="' . $file . '"');
header('Cache-Control: no-cache');
readfile($path);
