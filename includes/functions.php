<?php
// Suppress error display to prevent HTML output breaking JSON responses
error_reporting(E_ALL);
ini_set('display_errors', '0');
ini_set('log_errors', '1');

function generateId($length = 16): string {
    return bin2hex(random_bytes($length / 2));
}

function sendJson($data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function getFileExtension(string $filename): string {
    return strtolower(pathinfo($filename, PATHINFO_EXTENSION));
}

function validateAudioFile(array $file): ?string {
    if ($file['error'] !== UPLOAD_ERR_OK) {
        return '上传失败，错误代码: ' . $file['error'];
    }
    if ($file['size'] > MAX_UPLOAD_SIZE) {
        return '文件太大，最大支持 200MB';
    }
    $ext = getFileExtension($file['name']);
    if (!in_array($ext, ALLOWED_EXTENSIONS)) {
        return '不支持的文件格式: .' . $ext . '，支持: ' . implode(', ', ALLOWED_EXTENSIONS);
    }
    return null;
}

function runPython(string $script, array $args = []): array {
    $cmd = PYTHON_BIN . ' ' . escapeshellarg(PYTHON_DIR . '/' . $script);
    foreach ($args as $key => $value) {
        $cmd .= ' --' . $key . ' ' . escapeshellarg((string)$value);
    }
    $cmd .= ' 2>&1';

    $output = [];
    $exitCode = 0;
    $ret = exec($cmd, $output, $exitCode);

    return [
        'success' => $exitCode === 0,
        'code' => $exitCode,
        'output' => implode("\n", $output),
        'command' => $cmd
    ];
}

function getAudioInfo(string $filepath): array {
    $result = runPython('audio_utils.py', [
        'action' => 'analyze',
        'input' => $filepath
    ]);
    if ($result['success']) {
        $info = json_decode($result['output'], true);
        return $info ?: ['duration' => 0, 'sample_rate' => 0, 'channels' => 0];
    }
    return ['duration' => 0, 'sample_rate' => 0, 'channels' => 0];
}

function cleanTempFiles(string $jobId): void {
    $files = glob(TEMP_DIR . '/' . $jobId . '_*');
    foreach ($files as $f) {
        @unlink($f);
    }
}

function writeJobStatus(string $jobId, array $status): void {
    $file = TEMP_DIR . '/' . $jobId . '_status.json';
    file_put_contents($file, json_encode($status, JSON_UNESCAPED_UNICODE));
}

function readJobStatus(string $jobId): array {
    $file = TEMP_DIR . '/' . $jobId . '_status.json';
    if (!file_exists($file)) {
        return ['status' => 'not_found'];
    }
    return json_decode(file_get_contents($file), true) ?: ['status' => 'error'];
}
