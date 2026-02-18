/* dashboard.js - Dashboard view logic and polling */

const Dashboard = {
    _taskId: null,
    _pollTimer: null,
    _lastSeq: 0,
    _stageOrder: ['zotero_collect', 'mineru_upload', 'md_clean', 'smart_split', 'dify_upload', 'dify_index'],

    init() {
        document.getElementById('btn-start').addEventListener('click', () => this.startPipeline());
        document.getElementById('btn-cancel').addEventListener('click', () => this.cancelPipeline());
        document.getElementById('btn-check-zotero').addEventListener('click', () => this.checkZotero());
        document.getElementById('btn-select-zotero').addEventListener('click', () => this.openZoteroSelection());
        document.getElementById('btn-confirm-zotero-selection').addEventListener('click', () => this.confirmZoteroSelection());

        this.refreshVisionSummaryHint();
    },

    async refreshVisionSummaryHint() {
        const el = document.getElementById('vision-summary-hint');
        if (!el) return;

        try {
            const resp = await Api.getConfig();
            const cfg = resp.data || {};
            const imageCfg = cfg.image_summary || {};

            if (imageCfg.enabled === false) {
                this._showHint(el, 'warning', '图像视觉分析未启用：图片摘要将跳过视觉模型，仅基于文本文证回写。');
                return;
            }

            const hasApiKey = !!(imageCfg.api_key && String(imageCfg.api_key).trim());
            const hasModel = !!(imageCfg.model && String(imageCfg.model).trim());
            if (!hasApiKey || !hasModel) {
                this._showHint(el, 'warning', '视觉模型未完整配置（API Key/Model）：图片摘要将使用文本回退模式。');
                return;
            }

            this._hideHint(el);
        } catch (err) {
            this._showHint(el, 'warning', '无法读取图摘要配置，当前将按默认逻辑执行。');
        }
    },

    _showHint(el, type, message) {
        if (!el) return;
        el.classList.remove('d-none', 'alert-info', 'alert-warning', 'alert-danger', 'alert-success');
        if (type === 'info') el.classList.add('alert-info');
        else if (type === 'danger') el.classList.add('alert-danger');
        else if (type === 'success') el.classList.add('alert-success');
        else el.classList.add('alert-warning');
        el.textContent = message;
    },

    _hideHint(el) {
        if (!el) return;
        el.classList.add('d-none');
        el.textContent = '';
    },

    async openZoteroSelection() {
        const modal = new bootstrap.Modal(document.getElementById('zotero-collection-modal'));
        modal.show();
        await this.loadZoteroCollections();
    },

    async loadZoteroCollections() {
        const container = document.getElementById('zotero-collection-list');
        container.innerHTML = '<div class="text-center text-muted py-3">加载中...</div>';
        try {
            const resp = await Api.getCollections();
            const collections = resp.data || [];
            if (collections.length === 0) {
                container.innerHTML = '<div class="text-center text-muted py-3">未找到分组或连接失败</div>';
                return;
            }

            container.innerHTML = '';
            collections.sort((a, b) => (a.name || '').localeCompare(b.name || ''));

            for (const item of collections) {
                const el = document.createElement('label');
                el.className = 'list-group-item d-flex align-items-center gap-2';
                el.style.cursor = 'pointer';

                const checkbox = document.createElement('input');
                checkbox.className = 'form-check-input flex-shrink-0';
                checkbox.type = 'checkbox';
                checkbox.value = item.key;

                const currentKeys = document.getElementById('collection-keys').value.split(',').map(k => k.trim());
                if (currentKeys.includes(item.key)) {
                    checkbox.checked = true;
                }

                const content = document.createElement('div');
                content.className = 'd-flex flex-column';
                const name = document.createElement('span');
                name.className = 'fw-medium';
                name.textContent = item.name;
                content.appendChild(name);

                el.appendChild(checkbox);
                el.appendChild(content);
                container.appendChild(el);
            }
        } catch (err) {
            container.innerHTML = `<div class="text-danger py-3">加载失败: ${Utils.escape(err.message)}</div>`;
        }
    },

    confirmZoteroSelection() {
        const checkboxes = document.querySelectorAll('#zotero-collection-list input[type="checkbox"]:checked');
        const keys = Array.from(checkboxes).map(cb => cb.value);
        document.getElementById('collection-keys').value = keys.join(', ');
        const modalEl = document.getElementById('zotero-collection-modal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) modal.hide();
    },

    async startPipeline() {
        const keys = document.getElementById('collection-keys').value.trim();
        const collectionKeys = keys ? keys.split(',').map(k => k.trim()).filter(Boolean) : [];

        try {
            await this.refreshVisionSummaryHint();
            document.getElementById('btn-start').disabled = true;
            const resp = await Api.createTask(collectionKeys);
            this._taskId = resp.task_id;
            this._lastSeq = 0;
            this.clearUI();
            this.startPolling();
            document.getElementById('btn-cancel').disabled = false;
            Utils.showToast('流程已启动', 'success');
        } catch (err) {
            Utils.showToast(err.message, 'error');
            document.getElementById('btn-start').disabled = false;
        }
    },

    async cancelPipeline() {
        if (!this._taskId) return;
        try {
            await Api.cancelTask(this._taskId);
            Utils.showToast('任务已取消', 'warn');
        } catch (err) {
            Utils.showToast(err.message, 'error');
        }
    },

    async checkZotero() {
        const el = document.getElementById('zotero-status');
        el.textContent = '检查中...';
        try {
            const resp = await Api.checkZotero();
            el.textContent = resp.connected ? '已连接' : '未连接';
            el.className = resp.connected ? 'text-success' : 'text-danger';
        } catch (err) {
            el.textContent = '错误: ' + err.message;
            el.className = 'text-danger';
        }
    },

    startPolling() {
        this.stopPolling();
        this._pollTimer = setInterval(() => this.poll(), 2000);
        this.poll();
    },

    stopPolling() {
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
    },

    async poll() {
        if (!this._taskId) return;
        try {
            const taskResp = await Api.getTask(this._taskId);
            const task = taskResp.data;
            this.updateStats(task.stats);
            this.updateStepper(task.stage, task.status);
            this.updateFiles(task.files || []);
            this.updateRuntimeProgressHint(task);
            this.updateImageAiRuntimeHint(task);

            const eventsResp = await Api.getEvents(this._taskId, this._lastSeq);
            const events = eventsResp.data || [];
            if (events.length > 0) {
                this.appendEvents(events);
                this._lastSeq = events[events.length - 1].seq;
            }

            const terminal = ['succeeded', 'failed', 'cancelled', 'partial_succeeded'];
            if (terminal.includes(task.status)) {
                this.stopPolling();
                document.getElementById('btn-start').disabled = false;
                document.getElementById('btn-cancel').disabled = true;
                Utils.showToast(`任务 ${task.status}`, task.status === 'succeeded' ? 'success' : 'warn');
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    },

    updateRuntimeProgressHint(task) {
        const el = document.getElementById('runtime-progress-hint');
        if (!el || !task) return;

        const stage = task.stage;
        const status = task.status;
        const stats = task.stats || {};

        if (status === 'running' && stage === 'dify_upload') {
            this._showHint(el, 'info', 'Dify 上传中：文档正在提交，随后会进入入库处理。');
            return;
        }
        if (status === 'running' && stage === 'dify_index') {
            this._showHint(el, 'info', 'Dify 入库处理中：系统会在每个文件入库完成后逐个反馈结果。');
            return;
        }

        if (['failed', 'partial_succeeded'].includes(status) && (stats.failed || 0) > 0) {
            this._showHint(el, 'warning', '存在失败文件。可再次点击“开始流程”重试，已成功文件会自动跳过。');
            return;
        }

        if (status === 'succeeded') {
            this._showHint(el, 'success', '全部文件处理完成并已入库。');
            return;
        }

        this._hideHint(el);
    },

    updateImageAiRuntimeHint(task) {
        const el = document.getElementById('image-ai-runtime-hint');
        if (!el || !task) return;

        const imageAi = (task.stats || {}).image_ai;
        if (!imageAi || typeof imageAi !== 'object') {
            this._hideHint(el);
            return;
        }

        if (imageAi.enabled === false) {
            this._showHint(el, 'warning', '图像AI摘要未启用：本次图片摘要使用程序回退模式。');
            return;
        }

        const totalImages = Number(imageAi.total_images || 0);
        const attempted = Number(imageAi.ai_attempted || 0);
        const succeeded = Number(imageAi.ai_succeeded || 0);
        const failed = Number(imageAi.ai_failed || 0);
        const fallback = Number(imageAi.fallback_used || 0);

        if (totalImages === 0) {
            this._hideHint(el);
            return;
        }

        const msg = `图像AI摘要结果：检测 ${totalImages} 张，调用 ${attempted} 次，成功 ${succeeded}，失败 ${failed}，回退 ${fallback}。`;
        if (failed > 0) {
            this._showHint(el, 'warning', msg);
            return;
        }
        if (attempted > 0) {
            this._showHint(el, 'success', msg);
            return;
        }
        this._showHint(el, 'info', `图像摘要检测到 ${totalImages} 张图片，但未调用视觉模型，已使用程序回退摘要。`);
    },

    clearUI() {
        document.getElementById('stat-pending').textContent = '0';
        document.getElementById('stat-succeeded').textContent = '0';
        document.getElementById('stat-failed').textContent = '0';
        document.getElementById('event-log').innerHTML = '';
        document.getElementById('event-count').textContent = '0 事件';
        document.getElementById('file-list').innerHTML = '';
        document.querySelectorAll('.pipeline-stepper .step').forEach(s => {
            s.className = 'step';
            s.querySelector('.step-icon').innerHTML = '&#9675;';
        });
        this._hideHint(document.getElementById('runtime-progress-hint'));
        this._hideHint(document.getElementById('image-ai-runtime-hint'));
    },

    updateStats(stats) {
        if (!stats) return;
        document.getElementById('stat-pending').textContent = stats.pending || 0;
        document.getElementById('stat-succeeded').textContent = stats.succeeded || 0;
        document.getElementById('stat-failed').textContent = stats.failed || 0;
    },

    updateStepper(currentStage, taskStatus) {
        let idx = this._stageOrder.indexOf(currentStage);
        if (idx < 0 && ['succeeded', 'partial_succeeded', 'failed', 'cancelled'].includes(taskStatus)) {
            idx = this._stageOrder.length;
        }
        document.querySelectorAll('.pipeline-stepper .step').forEach((step, i) => {
            step.className = 'step';
            const icon = step.querySelector('.step-icon');
            if (i < idx) {
                step.classList.add('done');
                icon.innerHTML = '&#10003;';
            } else if (i === idx) {
                if (['failed', 'cancelled'].includes(taskStatus)) {
                    step.classList.add('error');
                    icon.innerHTML = '&#10007;';
                } else if (['succeeded', 'partial_succeeded'].includes(taskStatus)) {
                    step.classList.add('done');
                    icon.innerHTML = '&#10003;';
                } else {
                    step.classList.add('active');
                    icon.innerHTML = '&#9881;';
                }
            } else {
                icon.innerHTML = '&#9675;';
            }
        });
    },

    appendEvents(events) {
        const log = document.getElementById('event-log');
        for (const evt of events) {
            const line = document.createElement('div');
            line.className = `event-line level-${evt.level}`;
            const time = Utils.formatTime(evt.ts);
            line.textContent = `[${time}] [${evt.stage}] ${evt.message}`;
            log.appendChild(line);
        }
        log.scrollTop = log.scrollHeight;
        const total = log.querySelectorAll('.event-line').length;
        document.getElementById('event-count').textContent = `${total} 事件`;
    },

    updateFiles(files) {
        const container = document.getElementById('file-list');
        container.innerHTML = '';
        for (const f of files) {
            const stageText = Utils.formatStage ? Utils.formatStage(f.stage) : (f.stage || '-');
            const retryTip = f.status === 'failed'
                ? '<small class="text-warning d-block mt-1">可重试：再次启动流程会自动重试该失败文件</small>'
                : '';

            const card = document.createElement('div');
            card.className = 'col';
            card.innerHTML = `
                <div class="card file-card">
                    <div class="card-body py-2 px-3">
                        <div class="d-flex justify-content-between align-items-center gap-2">
                            <span class="text-truncate" style="max-width:60%">${Utils.escape(f.filename)}</span>
                            ${Utils.formatStatus(f.status)}
                        </div>
                        <small class="text-muted">阶段：${Utils.escape(stageText)}</small>
                        ${f.error ? `<small class="text-danger d-block">${Utils.escape(f.error)}</small>` : ''}
                        ${retryTip}
                    </div>
                </div>`;
            container.appendChild(card);
        }
    }
};
