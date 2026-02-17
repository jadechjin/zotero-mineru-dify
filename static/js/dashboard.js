/* dashboard.js — Dashboard view logic and polling */

const Dashboard = {
    _taskId: null,
    _pollTimer: null,
    _lastSeq: 0,
    _stageOrder: ['zotero_collect', 'mineru_upload', 'md_clean', 'smart_split', 'dify_upload'],

    init() {
        document.getElementById('btn-start').addEventListener('click', () => this.startPipeline());
        document.getElementById('btn-cancel').addEventListener('click', () => this.cancelPipeline());
        document.getElementById('btn-check-zotero').addEventListener('click', () => this.checkZotero());
        document.getElementById('btn-select-zotero').addEventListener('click', () => this.openZoteroSelection());
        document.getElementById('btn-confirm-zotero-selection').addEventListener('click', () => this.confirmZoteroSelection());
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

            // Helper to build tree
            const renderTree = (items, level = 0) => {
                for (const item of items) {
                    const indent = level * 20;
                    const el = document.createElement('label');
                    el.className = 'list-group-item d-flex align-items-center gap-2';
                    el.style.paddingLeft = `${indent + 12}px`;
                    el.style.cursor = 'pointer';

                    const checkbox = document.createElement('input');
                    checkbox.className = 'form-check-input flex-shrink-0';
                    checkbox.type = 'checkbox';
                    checkbox.value = item.key;
                    checkbox.dataset.name = item.name;

                    // Check if currently selected
                    const currentKeys = document.getElementById('collection-keys').value.split(',').map(k => k.trim());
                    if (currentKeys.includes(item.key)) {
                        checkbox.checked = true;
                    }

                    const span = document.createElement('span');
                    span.textContent = item.name;

                    el.appendChild(checkbox);
                    el.appendChild(span);
                    container.appendChild(el);

                    if (item.children && item.children.length > 0) {
                        renderTree(item.children, level + 1);
                    }
                }
            };

            // Build hierarchy from flat list if needed, or assume backend returns tree
            // The backend returns a list, let's treat it as flat for now or assume backend handles tree structure.
            // Backend `services/zotero_client.py` returns a flat list usually, but let's check `web/routes/zotero_api.py`.
            // The `list_collections` in `zotero_client.py` seems to return a flat list.
            // But usually Zotero collections have `parentCollection` field.
            // Let's build a simple tree here if possible, or just list them.
            // For simplicity and robustness, let's just list them flat with parent indication if available,
            // OR relies on `services/zotero_client.py` to return them.
            // Actually `list_collections` fetches all.
            // Let's just render them flat for now, as tree building might be complex without seeing data.
            // WAIT, `zotero_client.py`'s `list_collections` fetches all. 
            // Let's just render them.

            // To make it nicer, let's just render flat list sorted by name.
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
                const key = document.createElement('small');
                key.className = 'text-muted';
                key.textContent = item.key;

                content.appendChild(name);
                // content.appendChild(key); // Optional: hide key to be cleaner

                el.appendChild(checkbox);
                el.appendChild(content);
                container.appendChild(el);
            }

        } catch (err) {
            container.innerHTML = `<div class="text-danger py-3">加载失败: ${err.message}</div>`;
        }
    },

    confirmZoteroSelection() {
        const checkboxes = document.querySelectorAll('#zotero-collection-list input[type="checkbox"]:checked');
        const keys = Array.from(checkboxes).map(cb => cb.value);
        document.getElementById('collection-keys').value = keys.join(', ');
        // Close modal
        const modalEl = document.getElementById('zotero-collection-modal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        modal.hide();
    },

    async startPipeline() {
        const keys = document.getElementById('collection-keys').value.trim();
        const collectionKeys = keys ? keys.split(',').map(k => k.trim()).filter(Boolean) : [];

        try {
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
    },

    updateStats(stats) {
        if (!stats) return;
        document.getElementById('stat-pending').textContent = stats.pending || 0;
        document.getElementById('stat-succeeded').textContent = stats.succeeded || 0;
        document.getElementById('stat-failed').textContent = stats.failed || 0;
    },

    updateStepper(currentStage, taskStatus) {
        const idx = this._stageOrder.indexOf(currentStage);
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
            const card = document.createElement('div');
            card.className = 'col';
            card.innerHTML = `
                <div class="card file-card">
                    <div class="card-body py-2 px-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="text-truncate" style="max-width:70%">${Utils.escape(f.filename)}</span>
                            ${Utils.formatStatus(f.status)}
                        </div>
                        ${f.error ? `<small class="text-danger">${Utils.escape(f.error)}</small>` : ''}
                    </div>
                </div>`;
            container.appendChild(card);
        }
    }
};
