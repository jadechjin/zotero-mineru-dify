/* config.js — Configuration view logic */

const _HEALTH_CHECK_MAP = {
    'zotero': { label: '测试 Zotero 连接', method: () => Api.checkZotero() },
    'mineru': { label: '测试 MinerU 连接', method: () => Api.checkMinerU() },
    'dify': { label: '测试 Dify 连接', method: () => Api.checkDify() },
    'image_summary': { label: '测试视觉模型连接', method: () => Api.checkImageSummary() },
};

const Config = {
    _schema: null,
    _categoryLabels: {},
    _currentData: {},
    _activeCategory: null,

    async init() {
        document.getElementById('btn-save-config').addEventListener('click', () => this.save());
        document.getElementById('btn-reset-config').addEventListener('click', () => this.reset());
        document.getElementById('btn-import-env').addEventListener('click', () => this.importEnv());
    },

    async load() {
        try {
            const [schemaResp, configResp] = await Promise.all([
                Api.getSchema(),
                Api.getConfig(),
            ]);
            this._schema = schemaResp.schema;
            this._categoryLabels = schemaResp.category_labels || {};
            this._currentData = configResp.data;
            this.renderTabs();
            this.renderForms();
        } catch (err) {
            Utils.showToast('加载配置失败: ' + err.message, 'error');
        }
    },

    renderTabs() {
        const container = document.getElementById('config-tabs');
        container.innerHTML = '';
        const categories = Object.keys(this._schema);
        categories.forEach((cat, i) => {
            const label = this._categoryLabels[cat] || cat;
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action' + (i === 0 ? ' active' : '');
            item.textContent = label;
            item.dataset.category = cat;
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.switchTab(cat);
            });
            container.appendChild(item);
        });
        this._activeCategory = categories[0];
    },

    switchTab(cat) {
        this._activeCategory = cat;
        document.querySelectorAll('#config-tabs .list-group-item').forEach(el => {
            el.classList.toggle('active', el.dataset.category === cat);
        });
        document.querySelectorAll('.config-category-form').forEach(el => {
            el.classList.toggle('active', el.dataset.category === cat);
        });
        // Scroll to top of config container or page
        window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    renderForms() {
        const container = document.getElementById('config-form-container');
        container.innerHTML = '';

        for (const [cat, fields] of Object.entries(this._schema)) {
            const form = document.createElement('div');
            form.className = 'config-category-form' + (cat === this._activeCategory ? ' active' : '');
            form.dataset.category = cat;

            // Add connectivity test button for service categories
            const hc = _HEALTH_CHECK_MAP[cat];
            if (hc) {
                const testRow = document.createElement('div');
                testRow.className = 'd-flex align-items-center gap-2 mb-3 pb-2 border-bottom';

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn btn-outline-info btn-sm';
                btn.textContent = hc.label;

                const statusEl = document.createElement('span');
                statusEl.className = 'text-muted small';
                statusEl.textContent = '(测试使用已保存的配置)';

                btn.addEventListener('click', async () => {
                    btn.disabled = true;
                    statusEl.textContent = '检查中...';
                    statusEl.className = 'text-muted small';
                    try {
                        const resp = await hc.method();
                        const connected = resp.connected;
                        const message = resp.message || (connected ? '已连接' : '未连接');
                        statusEl.textContent = message;
                        statusEl.className = connected ? 'text-success small' : 'text-danger small';
                        Utils.showToast(message, connected ? 'success' : 'error');
                    } catch (err) {
                        statusEl.textContent = '错误: ' + err.message;
                        statusEl.className = 'text-danger small';
                        Utils.showToast('连接测试失败: ' + err.message, 'error');
                    } finally {
                        btn.disabled = false;
                    }
                });

                testRow.appendChild(btn);
                testRow.appendChild(statusEl);
                form.appendChild(testRow);
            }

            for (const [key, spec] of Object.entries(fields)) {
                const value = (this._currentData[cat] || {})[key];
                const group = document.createElement('div');
                group.className = 'form-group';

                const label = document.createElement('label');
                label.textContent = spec.label || key;
                label.htmlFor = `cfg-${cat}-${key}`;
                group.appendChild(label);

                let input;
                if (spec.type === 'bool') {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'form-check form-switch';
                    input = document.createElement('input');
                    input.type = 'checkbox';
                    input.className = 'form-check-input';
                    input.id = `cfg-${cat}-${key}`;
                    input.checked = !!value;
                    input.dataset.fieldType = 'bool';
                    wrapper.appendChild(input);
                    group.appendChild(wrapper);
                } else if (spec.type === 'select') {
                    input = document.createElement('select');
                    input.className = 'form-select';
                    input.id = `cfg-${cat}-${key}`;
                    (spec.options || []).forEach(opt => {
                        const option = document.createElement('option');
                        option.value = opt;
                        option.textContent = opt;
                        option.selected = opt === value;
                        input.appendChild(option);
                    });
                    input.dataset.fieldType = 'select';
                    group.appendChild(input);
                } else if (spec.type === 'int' || spec.type === 'float') {
                    input = document.createElement('input');
                    input.type = 'number';
                    input.className = 'form-control';
                    input.id = `cfg-${cat}-${key}`;
                    input.value = value != null ? value : '';
                    if (spec.min != null) input.min = spec.min;
                    if (spec.max != null) input.max = spec.max;
                    if (spec.type === 'float') input.step = '0.1';
                    input.dataset.fieldType = spec.type;
                    group.appendChild(input);
                } else {
                    input = document.createElement('input');
                    input.type = spec.sensitive ? 'password' : 'text';
                    input.className = 'form-control';
                    input.id = `cfg-${cat}-${key}`;
                    input.value = value != null ? value : '';
                    input.dataset.fieldType = 'str';
                    group.appendChild(input);
                }

                input.dataset.category = cat;
                input.dataset.key = key;
                form.appendChild(group);
            }

            container.appendChild(form);
        }
    },

    collectValues() {
        const result = {};
        document.querySelectorAll('#config-form-container [data-category]').forEach(el => {
            if (!el.dataset.key) return;
            const cat = el.dataset.category;
            const key = el.dataset.key;

            const ft = el.dataset.fieldType;
            if (ft === 'bool') {
                if (!result[cat]) result[cat] = {};
                result[cat][key] = el.checked;
            } else if (ft === 'int') {
                if (!result[cat]) result[cat] = {};
                result[cat][key] = parseInt(el.value, 10) || 0;
            } else if (ft === 'float') {
                if (!result[cat]) result[cat] = {};
                result[cat][key] = parseFloat(el.value) || 0;
            } else {
                const value = (el.value || '').trim();
                // Sensitive fields are returned masked by backend.
                // Keep existing secret when user leaves it unchanged.
                if (el.type === 'password') {
                    const looksMasked = /^\*{4,}.{4}$/.test(value);
                    if (!value || looksMasked) {
                        return;
                    }
                }
                if (!result[cat]) result[cat] = {};
                result[cat][key] = el.value;
            }
        });
        return result;
    },

    async save() {
        try {
            const patch = this.collectValues();
            const resp = await Api.updateConfig(patch);
            this._currentData = resp.data;
            Utils.showToast('配置已保存', 'success');
        } catch (err) {
            Utils.showToast('保存失败: ' + err.message, 'error');
        }
    },

    async reset() {
        if (!confirm('确定要重置所有配置为默认值吗？')) return;
        try {
            const resp = await Api.resetConfig();
            this._currentData = resp.data;
            this.renderForms();
            Utils.showToast('配置已重置为默认值', 'success');
        } catch (err) {
            Utils.showToast('重置失败: ' + err.message, 'error');
        }
    },

    async importEnv() {
        try {
            const resp = await Api.importEnv('.env');
            this._currentData = resp.data;
            this.renderForms();
            Utils.showToast('.env 已导入', 'success');
        } catch (err) {
            Utils.showToast('导入失败: ' + err.message, 'error');
        }
    }
};
