<?php
define('BASE_PATH', __DIR__);
define('UPLOAD_DIR', BASE_PATH . '/uploads');
define('OUTPUT_DIR', BASE_PATH . '/outputs');
define('TEMP_DIR', BASE_PATH . '/temp');
define('PYTHON_DIR', BASE_PATH . '/python');
define('MMM_BIN', 'mmm');
define('MMM_DIR', dirname(BASE_PATH) . '/mmm');
// Auto-detect Python binary (checks python3 first, then python)
// Add custom paths here if your Python is not on PATH
$python_paths = [
    'python3',
    'python',
];
$python_bin = 'python';
foreach ($python_paths as $p) {
    $test = exec(escapeshellarg($p) . ' -c "print(1)" 2>&1', $dummy, $code);
    if ($code === 0) {
        $python_bin = $p;
        break;
    }
}
define('PYTHON_BIN', $python_bin);
define('MAX_UPLOAD_SIZE', 200 * 1024 * 1024); // 200MB
define('ALLOWED_TYPES', ['audio/wav', 'audio/mpeg', 'audio/flac', 'audio/x-wav', 'audio/mp3', 'audio/x-flac', 'audio/ogg', 'audio/aac']);
define('ALLOWED_EXTENSIONS', ['wav', 'mp3', 'flac', 'ogg', 'aac', 'm4a']);
define('VERSION', '1.5.0');
define('VERSION_DATE', '2026-06-08');

// 12 processing modules
define('MODULES', [
    'suno_specialist'    => 'Suno声乐专家',
    'ai_to_human'        => 'AI转真人引擎',
    'deep_purify'        => '深度提存',
    'vocal_eq'           => '人声EQ',
    'label_purify'       => 'AI原标签净化',
    'smart_optimize'     => '智能音质一键优化',
    'ai_mastering'       => 'AI母带处理器',
    'pro_tools'          => '专业工具Pro',
    'neural_fingerprint' => 'AI神经指纹去除',
    'cover_engine'       => '翻唱音频处理引擎',
    'batch_processor'    => '批量处理工作站',
    'smart_mixer'        => '智能混音处理器',
    'bass_enhancer'      => '低频增强处理器'
]);

// Processing presets
define('PRESETS', [
    'light'  => ['intensity' => 0.3, 'label' => '轻度处理'],
    'medium' => ['intensity' => 0.6, 'label' => '中度处理'],
    'heavy'  => ['intensity' => 1.0, 'label' => '深度处理']
]);
