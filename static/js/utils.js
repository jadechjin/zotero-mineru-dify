/* utils.js - toast notifications and helper functions */

const Utils = {
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const id = 'toast-' + Date.now();
        const bgClass = {
            success: 'bg-success text-white',
            error: 'bg-danger text-white',
            warn: 'bg-warning text-dark',
            info: 'bg-info text-dark',
        }[type] || 'bg-secondary text-white';

        const html = `
            <div id="${id}" class="toast ${bgClass}" role="alert" data-bs-autohide="true" data-bs-delay="4000">
                <div class="toast-body d-flex justify-content-between align-items-center">
                    <span>${this.escape(message)}</span>
                    <button type="button" class="btn-close btn-close-white ms-2" onclick="this.closest('.toast').remove()"></button>
                </div>
            </div>`;
        container.insertAdjacentHTML('beforeend', html);
        const el = document.getElementById(id);
        setTimeout(() => el && el.remove(), 4500);
    },

    escape(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    formatTime(ts) {
        if (!ts) return '-';
        const d = new Date(ts * 1000);
        return d.toLocaleTimeString('zh-CN', { hour12: false });
    },

    formatStatus(status) {
        const map = {
            queued: '<span class="badge bg-secondary">排队中</span>',
            running: '<span class="badge bg-primary">运行中</span>',
            succeeded: '<span class="badge bg-success">成功</span>',
            failed: '<span class="badge bg-danger">失败</span>',
            cancelled: '<span class="badge bg-warning text-dark">已取消</span>',
            partial_succeeded: '<span class="badge bg-info">部分成功</span>',
            pending: '<span class="badge bg-secondary">等待中</span>',
            processing: '<span class="badge bg-primary">处理中</span>',
            skipped: '<span class="badge bg-light text-dark">已跳过</span>',
        };
        return map[status] || `<span class="badge bg-secondary">${this.escape(status || '-')}</span>`;
    },

    formatStage(stage) {
        const map = {
            init: '初始化',
            zotero_collect: '收集 Zotero',
            mineru_upload: 'MinerU 上传',
            mineru_poll: 'MinerU 轮询',
            md_clean: 'Markdown 清洗',
            smart_split: '智能分割',
            dify_upload: 'Dify 上传',
            dify_index: 'Dify 入库',
            finalize: '收尾',
        };
        return map[stage] || stage || '-';
    },

    truncate(str, maxLen = 60) {
        if (!str || str.length <= maxLen) return str || '';
        return str.substring(0, maxLen) + '...';
    }
};
