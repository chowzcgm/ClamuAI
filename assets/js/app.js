/**
 * ClamuAI - Frontend Application
 */
(function() {
    'use strict';

    var state = {
        jobId: null,
        filename: null,
        intensity: 0.88,
        isProcessing: false,
    };

    function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return document.querySelectorAll(sel); }

    // Only bind if element exists
    function on(el, event, fn) {
        if (el) el.addEventListener(event, fn);
    }

    // ========== Upload ==========
    var uploadZone = $('#uploadZone');
    var fileInput = $('#fileInput');
    var fileInfo = $('#fileInfo');
    var fileName = $('#fileName');
    var fileMeta = $('#fileMeta');
    var removeFile = $('#removeFile');

    on(uploadZone, 'click', function() { if (fileInput) fileInput.click(); });
    on(uploadZone, 'dragover', function(e) { e.preventDefault(); uploadZone.classList.add('drag-over'); });
    on(uploadZone, 'dragleave', function() { uploadZone.classList.remove('drag-over'); });
    on(uploadZone, 'drop', function(e) {
        e.preventDefault();
        uploadZone.classList.remove('drag-over');
        var file = e.dataTransfer.files[0];
        if (file) handleFile(file);
    });
    on(fileInput, 'change', function(e) {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });
    on(removeFile, 'click', resetFile);

    function handleFile(file) {
        if (!file) return;
        var fd = new FormData();
        fd.append('audio', file);
        fetch('index.php?action=upload', { method: 'POST', body: fd })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) { alert('上传失败: ' + data.error); return; }
                state.jobId = data.job_id;
                state.filename = data.filename;
                if (fileName) fileName.textContent = data.filename;
                if (fileMeta) fileMeta.textContent = formatSize(data.size) + ' | ' + data.duration + 's | ' + data.sample_rate + 'Hz | ' + data.channels + 'ch';
                if (fileInfo) fileInfo.style.display = 'flex';
                if (uploadZone) uploadZone.style.display = 'none';
                var btn = $('#smartOptimizeBtn');
                if (btn) btn.disabled = false;
            })
            .catch(function(err) { alert('上传失败: ' + err.message); });
    }

    function resetFile() {
        state.jobId = null;
        state.filename = null;
        if (fileInfo) fileInfo.style.display = 'none';
        if (uploadZone) uploadZone.style.display = 'block';
        if (fileInput) fileInput.value = '';
        var btn = $('#smartOptimizeBtn');
        if (btn) btn.disabled = true;
        var rs = $('#resultsSection');
        if (rs) rs.style.display = 'none';
        var qs = $('#queueSection');
        if (qs) qs.style.display = 'none';
    }

    // ========== Presets & Intensity ==========
    var presetBtns = $$('.preset-btn');
    var intensitySlider = $('#intensitySlider');
    var intensityValue = $('#intensityValue');
    var pipeline = $('#pipeline');

    presetBtns.forEach(function(btn) {
        on(btn, 'click', function() {
            presetBtns.forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
            var val = parseFloat(btn.getAttribute('data-preset'));
            state.intensity = val;
            if (intensitySlider) intensitySlider.value = val;
            if (intensityValue) intensityValue.textContent = val.toFixed(2);
            updatePipeline();
        });
    });

    on(intensitySlider, 'input', function() {
        var val = parseFloat(intensitySlider.value);
        state.intensity = val;
        if (intensityValue) intensityValue.textContent = val.toFixed(2);
        presetBtns.forEach(function(b) {
            var p = parseFloat(b.getAttribute('data-preset'));
            if (Math.abs(p - val) < 0.03) b.classList.add('active');
            else b.classList.remove('active');
        });
        updatePipeline();
    });

    function updatePipeline() {
        if (!pipeline) return;
        var stages = pipeline.querySelectorAll('.pv-stage');
        stages.forEach(function(s) {
            var min = parseFloat(s.getAttribute('data-min'));
            if (state.intensity >= min) s.classList.add('on');
            else s.classList.remove('on');
        });
    }
    updatePipeline();

    // ========== Processing ==========
    var smartOptimizeBtn = $('#smartOptimizeBtn');
    on(smartOptimizeBtn, 'click', startProcessing);

    function startProcessing() {
        if (!state.jobId || state.isProcessing) return;
        state.isProcessing = true;
        if (smartOptimizeBtn) smartOptimizeBtn.disabled = true;
        var rs = $('#resultsSection');
        if (rs) rs.style.display = 'none';

        showProgress(5, '引擎初始化...');
        addLog('启动处理引擎...');
        addLog('强度: ' + state.intensity.toFixed(2));

        var pollTimer = setInterval(function() {
            fetch('index.php?action=status&job_id=' + state.jobId)
                .then(function(r) { return r.json(); })
                .then(function(s) {
                    if (s.status === 'completed') {
                        clearInterval(pollTimer);
                        updateProgress(100, '处理完成');
                        if (s.log) s.log.forEach(function(l) { addLog(l); });
                        showResults(s);
                        state.isProcessing = false;
                    } else if (s.status === 'failed') {
                        clearInterval(pollTimer);
                        updateProgress(0, '处理失败');
                        addLog('失败: ' + (s.error || '未知错误'), true);
                        state.isProcessing = false;
                        if (smartOptimizeBtn) smartOptimizeBtn.disabled = false;
                    } else if (s.status === 'processing') {
                        updateProgress(50, s.current_module || '处理中...');
                    }
                })
                .catch(function() {});
        }, 2000);

        fetch('index.php?action=smart_optimize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: state.jobId, intensity: state.intensity })
        })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    clearInterval(pollTimer);
                    addLog('错误: ' + data.error, true);
                    updateProgress(0, '处理失败');
                    state.isProcessing = false;
                    if (smartOptimizeBtn) smartOptimizeBtn.disabled = false;
                } else if (data.status === 'completed') {
                    clearInterval(pollTimer);
                    updateProgress(100, '处理完成');
                    if (data.log) data.log.forEach(function(l) { addLog(l); });
                    showResults(data);
                    state.isProcessing = false;
                }
            })
            .catch(function(err) {
                clearInterval(pollTimer);
                addLog('错误: ' + err.message, true);
                state.isProcessing = false;
                if (smartOptimizeBtn) smartOptimizeBtn.disabled = false;
            });
    }

    // ========== Progress ==========
    function showProgress(pct, text) {
        var qs = $('#queueSection');
        if (qs) qs.style.display = 'block';
        var pb = $('#progressBar');
        if (pb) pb.style.width = pct + '%';
        var pt = $('#progressText');
        if (pt) pt.textContent = text;
        var pl = $('#progressLog');
        if (pl) pl.innerHTML = '';
    }

    function updateProgress(pct, text) {
        var pb = $('#progressBar');
        if (pb) pb.style.width = pct + '%';
        if (text) { var pt = $('#progressText'); if (pt) pt.textContent = text; }
    }

    function addLog(msg, isErr) {
        var pl = $('#progressLog');
        if (!pl) return;
        var li = document.createElement('li');
        li.textContent = msg;
        if (isErr) li.style.color = 'var(--danger)';
        pl.appendChild(li);
        pl.scrollTop = pl.scrollHeight;
    }

    // ========== Results ==========
    function showResults(data) {
        var rs = $('#resultsSection');
        if (rs) rs.style.display = 'block';
        var ri = $('#resultInfo');
        if (ri) ri.textContent = '文件: ' + (data.output_file || '');
        var db = $('#downloadBtn');
        if (db) {
            var url = data.output_url || 'index.php?action=download&file=' + encodeURIComponent(data.output_file || '');
            db.onclick = function() { window.open(url, '_blank'); };
        }

        // Show quality metrics if available
        if (data.quality && !data.quality.error) {
            var q = data.quality;
            var qm = $('#qualityMetrics');
            if (qm) qm.style.display = 'block';

            var pres = q.overall_music_preservation || 0;
            var qmp = $('#qmPreservation');
            if (qmp) { qmp.textContent = pres.toFixed(1) + '%'; qmp.style.color = pres > 80 ? 'var(--success)' : pres > 60 ? 'var(--warning)' : 'var(--danger)'; }
            var qmpb = $('#qmPreservationBar');
            if (qmpb) { qmpb.style.width = Math.min(100, pres) + '%'; qmpb.style.background = pres > 80 ? 'var(--success)' : pres > 60 ? 'var(--warning)' : 'var(--danger)'; }

            var dis = q.watermark_disruption || 0;
            var qmd = $('#qmDisruption');
            if (qmd) { qmd.textContent = dis.toFixed(1) + '%'; qmd.style.color = dis > 60 ? 'var(--success)' : dis > 30 ? 'var(--warning)' : 'var(--text-muted)'; }
            var qmdb = $('#qmDisruptionBar');
            if (qmdb) { qmdb.style.width = Math.min(100, dis) + '%'; qmdb.style.background = dis > 60 ? 'var(--success)' : dis > 30 ? 'var(--warning)' : 'var(--text-muted)'; }

            var delta = q.ai_score ? q.ai_score.delta : null;
            var qad = $('#qmAiDelta');
            if (qad && delta !== null) { qad.textContent = (delta > 0 ? '+' : '') + delta.toFixed(1); qad.style.color = delta < 0 ? 'var(--success)' : 'var(--warning)'; }
        }

        if (rs) rs.scrollIntoView({ behavior: 'smooth' });
    }

    var newProcessBtn = $('#newProcessBtn');
    on(newProcessBtn, 'click', function() {
        resetFile();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // ========== Clear Cache ==========
    var clearCacheBtn = $('#clearCacheBtn');
    on(clearCacheBtn, 'click', function() {
        if (clearCacheBtn) { clearCacheBtn.disabled = true; clearCacheBtn.textContent = '⏳ 清理中...'; }

        fetch('index.php?action=clear_cache', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scope: 'temp' })
        })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    showToast('清理失败: ' + data.error, 'error');
                    return;
                }
                showToast('已清理 ' + data.cleared_count + ' 个临时文件', 'ok');
                resetFile();
            })
            .catch(function(err) {
                showToast('清理失败: ' + err.message, 'error');
            })
            .finally(function() {
                if (clearCacheBtn) { clearCacheBtn.disabled = false; clearCacheBtn.textContent = '🧹 清理缓存'; }
            });
    });

    // Simple toast notification (auto-dismiss)
    function showToast(msg, type) {
        var existing = $('#toastMsg');
        if (existing) existing.remove();
        var toast = document.createElement('div');
        toast.id = 'toastMsg';
        toast.textContent = msg;
        toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:10px 24px;'
            + 'border-radius:8px;font-size:14px;z-index:9999;transition:opacity 0.3s;'
            + (type === 'error'
                ? 'background:#f87171;color:#fff;'
                : 'background:#34d399;color:#111;');
        document.body.appendChild(toast);
        setTimeout(function() { toast.style.opacity = '0'; }, 2000);
        setTimeout(function() { if (toast.parentNode) toast.remove(); }, 2300);
    }

    function formatSize(b) {
        if (b < 1024) return b + ' B';
        if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
        return (b / 1048576).toFixed(1) + ' MB';
    }
})();
