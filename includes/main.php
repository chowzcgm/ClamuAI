<div class="main-layout">
    <div class="panel panel-left">
        <section class="upload-section">
            <h2>上传音频</h2>
            <div class="upload-zone" id="uploadZone">
                <div class="upload-icon">
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                        <path d="M24 32V16M16 24l8-8 8 8" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M8 36v-4a4 4 0 014-4h24a4 4 0 014 4v4" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
                    </svg>
                </div>
                <p>拖拽音频文件到此处，或点击上传</p>
                <span class="upload-hint">支持 WAV / MP3 / FLAC / OGG / AAC / M4A，最大 200MB</span>
                <input type="file" id="fileInput" accept=".wav,.mp3,.flac,.ogg,.aac,.m4a" hidden>
            </div>
            <div class="file-info" id="fileInfo" style="display:none">
                <span class="file-name" id="fileName"></span>
                <span class="file-meta" id="fileMeta"></span>
                <button class="btn btn-sm btn-outline" id="removeFile">移除</button>
            </div>
        </section>

        <section class="preset-section">
            <h2>处理管线</h2>
            <div class="preset-buttons">
                <button class="btn preset-btn" data-preset="0.5">标准</button>
                <button class="btn preset-btn" data-preset="0.7">增强</button>
                <button class="btn preset-btn active" data-preset="0.88">过检测</button>
            </div>
            <input type="range" class="intensity-slider" id="intensitySlider" min="0.3" max="1.0" step="0.05" value="0.88">
            <div class="intensity-label">
                <span>标准=轻处理 · 增强=时序相位 · 过检测=全管线</span>
                <span id="intensityValue">0.88</span>
            </div>
            <div class="pipeline-viz" id="pipeline">
                <span class="pv-stage" data-min="0.5">移调</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.5">拉伸</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.6">饱和</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.7">相位</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.75">频谱</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.8">44.1k</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.8">立体声</span><span class="pv-arrow">→</span>
                <span class="pv-stage" data-min="0.5">母带</span>
            </div>
        </section>

        <section class="action-section">
            <button class="btn btn-primary btn-lg btn-full" id="smartOptimizeBtn" disabled>
                开始处理
            </button>
        </section>
    </div>

    <div class="panel panel-right">
        <section class="modules-section" id="modulesSection">
            <h2>处理模块</h2>
            <p style="color:var(--text-muted);font-size:13px;text-align:center;padding:20px 0;">
                管线已自动配置<br>选择左侧强度即可
            </p>
        </section>

        <section class="queue-section" id="queueSection" style="display:none">
            <h2>处理进度</h2>
            <div class="progress-bar-container">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <p class="progress-text" id="progressText">初始化...</p>
            <ul class="progress-log" id="progressLog"></ul>
        </section>

        <section class="results-section" id="resultsSection" style="display:none">
            <h2>处理完成</h2>
            <div class="result-card">
                <div class="result-actions">
                    <span class="result-info" id="resultInfo"></span>
                    <button class="btn btn-primary" id="downloadBtn">下载处理结果</button>
                    <button class="btn btn-outline" id="newProcessBtn">处理新文件</button>
                </div>
                <div class="quality-metrics" id="qualityMetrics" style="display:none">
                    <div class="qm-row">
                        <span class="qm-label">音乐保留度</span>
                        <span class="qm-value" id="qmPreservation">--</span>
                        <span class="qm-bar"><span class="qm-fill" id="qmPreservationBar"></span></span>
                    </div>
                    <div class="qm-row">
                        <span class="qm-label">水印破坏度</span>
                        <span class="qm-value" id="qmDisruption">--</span>
                        <span class="qm-bar"><span class="qm-fill" id="qmDisruptionBar"></span></span>
                    </div>
                    <div class="qm-row">
                        <span class="qm-label">AI痕迹分数变化</span>
                        <span class="qm-value" id="qmAiDelta">--</span>
                    </div>
                </div>
            </div>
        </section>
    </div>
</div>
