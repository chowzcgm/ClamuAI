<?php
require_once __DIR__ . '/config.php';

// Simple router
$action = $_GET['action'] ?? 'home';

// Security: validate action
$allowed_actions = ['home', 'upload', 'process', 'smart_optimize', 'download', 'status', 'check', 'spectrogram', 'records', 'clear_cache'];
if (!in_array($action, $allowed_actions)) {
    $action = 'home';
}

// Route to appropriate handler
switch ($action) {
    case 'upload':
        require __DIR__ . '/modules/upload.php';
        break;
    case 'process':
        require __DIR__ . '/modules/process.php';
        break;
    case 'smart_optimize':
        require __DIR__ . '/modules/smart_optimize.php';
        break;
    case 'download':
        require __DIR__ . '/modules/download.php';
        break;
    case 'status':
        require __DIR__ . '/modules/status.php';
        break;
    case 'check':
        require __DIR__ . '/modules/check.php';
        break;
    case 'spectrogram':
        require __DIR__ . '/modules/spectrogram.php';
        break;
    case 'records':
        require __DIR__ . '/modules/records.php';
        break;
    case 'clear_cache':
        require __DIR__ . '/modules/clear_cache.php';
        break;
    default:
        // Render main page
        require __DIR__ . '/includes/header.php';
        require __DIR__ . '/includes/main.php';
        require __DIR__ . '/includes/footer.php';
        break;
}
