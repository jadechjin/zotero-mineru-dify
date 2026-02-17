/* main.js — App initialization and routing */

document.addEventListener('DOMContentLoaded', () => {
    Dashboard.init();
    Config.init();

    // Navigation
    document.querySelectorAll('[data-view]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const view = e.target.dataset.view;
            switchView(view);
        });
    });
});

function switchView(view) {
    document.getElementById('view-dashboard').classList.toggle('d-none', view !== 'dashboard');
    document.getElementById('view-config').classList.toggle('d-none', view !== 'config');

    document.querySelectorAll('[data-view]').forEach(link => {
        link.classList.toggle('active', link.dataset.view === view);
    });

    if (view === 'config') {
        Config.load();
    }
}
