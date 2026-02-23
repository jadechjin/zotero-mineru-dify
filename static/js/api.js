/* api.js — API request wrapper */

const API_BASE = '/api/v1';

const Api = {
    async request(method, path, body = null) {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body !== null) {
            opts.body = JSON.stringify(body);
        }
        const resp = await fetch(API_BASE + path, opts);
        const data = await resp.json();
        if (!resp.ok || data.success === false) {
            throw new Error(data.error || `HTTP ${resp.status}`);
        }
        return data;
    },

    getConfig() { return this.request('GET', '/config'); },
    updateConfig(patch) { return this.request('PUT', '/config', patch); },
    getSchema() { return this.request('GET', '/config/schema'); },
    importEnv(path) { return this.request('POST', '/config/import-env', { path }); },
    resetConfig() { return this.request('POST', '/config/reset'); },

    createTask(collectionKeys) {
        return this.request('POST', '/tasks', { collection_keys: collectionKeys });
    },
    listTasks() { return this.request('GET', '/tasks'); },
    getTask(id) { return this.request('GET', `/tasks/${id}`); },
    getEvents(id, afterSeq) { return this.request('GET', `/tasks/${id}/events?after_seq=${afterSeq}`); },
    getFiles(id) { return this.request('GET', `/tasks/${id}/files`); },
    cancelTask(id) { return this.request('POST', `/tasks/${id}/cancel`); },
    skipFile(taskId, filename) {
        return this.request('POST', `/tasks/${taskId}/files/${encodeURIComponent(filename)}/skip`);
    },

    checkZotero() { return this.request('GET', '/zotero/health'); },
    checkMinerU() { return this.request('GET', '/mineru/health'); },
    checkDify() { return this.request('GET', '/dify/health'); },
    checkImageSummary() { return this.request('GET', '/image-summary/health'); },
    getCollections() { return this.request('GET', '/zotero/collections'); },
};
