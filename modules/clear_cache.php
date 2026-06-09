<?php
/**
 * Clear Cache Module — Clean up temp files, status JSONs, and optional uploads/outputs.
 */
require_once __DIR__ . '/../includes/functions.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sendJson(['error' => '仅支持 POST 请求'], 405);
}

$input = json_decode(file_get_contents('php://input'), true);
$scope = $input['scope'] ?? 'temp'; // temp | all

$cleared = [];
$errors = [];

// Always clear temp status files
$tempFiles = glob(TEMP_DIR . '/*_status.json');
$tempLogs  = glob(TEMP_DIR . '/*.log');
$allTemp = array_merge($tempFiles, $tempLogs);
foreach ($allTemp as $f) {
    if (@unlink($f)) {
        $cleared[] = basename($f);
    } else {
        $errors[] = basename($f);
    }
}

// If scope=all, also clear uploads and outputs
if ($scope === 'all') {
    $uploadFiles = glob(UPLOAD_DIR . '/*');
    foreach ($uploadFiles as $f) {
        if (is_file($f) && @unlink($f)) {
            $cleared[] = 'uploads/' . basename($f);
        }
    }
    $outputFiles = glob(OUTPUT_DIR . '/*');
    foreach ($outputFiles as $f) {
        if (is_file($f) && @unlink($f)) {
            $cleared[] = 'outputs/' . basename($f);
        }
    }
}

sendJson([
    'status' => 'ok',
    'scope' => $scope,
    'cleared_count' => count($cleared),
    'cleared' => $cleared,
    'errors' => $errors
]);
