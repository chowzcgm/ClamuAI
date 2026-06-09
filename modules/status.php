<?php
require_once __DIR__ . '/../includes/functions.php';

$jobId = $_GET['job_id'] ?? '';
$jobId = preg_replace('/[^a-f0-9]/', '', $jobId);

if (!$jobId) {
    sendJson(['error' => '缺少 job_id'], 400);
}

$status = readJobStatus($jobId);
sendJson($status);
