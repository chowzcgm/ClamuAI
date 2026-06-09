<?php
/**
 * Records module - List all past job records
 */
require_once __DIR__ . '/../includes/functions.php';

// Scan temp directory for status JSON files
$records = [];
$statusFiles = glob(TEMP_DIR . '/*_status.json');

foreach ($statusFiles as $statusFile) {
    $data = json_decode(file_get_contents($statusFile), true);
    if (!$data) continue;

    // Extract job ID from filename (e.g., "0f351f9d78cd62e1_status.json" -> "0f351f9d78cd62e1")
    $filename = basename($statusFile);
    $jobId = substr($filename, 0, -12); // remove "_status.json"

    // Check if uploaded and processed files still exist
    $uploads = glob(UPLOAD_DIR . '/' . $jobId . '.*');
    $outputs = glob(OUTPUT_DIR . '/' . $jobId . '_processed.*');

    $records[] = [
        'job_id' => $jobId,
        'status' => $data['status'] ?? 'unknown',
        'intensity' => $data['intensity'] ?? null,
        'threats_found' => $data['threats_found'] ?? 0,
        'patterns_suppressed' => $data['patterns_suppressed'] ?? 0,
        'quality_loss' => $data['quality_loss'] ?? 0,
        'log' => $data['log'] ?? [],
        'output_file' => $data['output_file'] ?? null,
        'output_url' => $data['output_url'] ?? null,
        'has_upload' => !empty($uploads),
        'has_output' => !empty($outputs),
        'mtime' => filemtime($statusFile)
    ];
}

// Sort by modification time, newest first
usort($records, function($a, $b) {
    return $b['mtime'] - $a['mtime'];
});

// Remove mtime from output (internal only)
$records = array_map(function($r) {
    $r['created_at'] = date('Y-m-d H:i:s', $r['mtime']);
    unset($r['mtime']);
    return $r;
}, $records);

sendJson(['records' => $records, 'total' => count($records)]);
