const navItems = document.querySelectorAll('.pill-nav-item');
const pill = document.querySelector('.nav-pill');
const contentTrack = document.querySelector('.content-track');
let activeIndex = 0;

function updatePill(element) {
    const rect = element.getBoundingClientRect();
    const parentRect = element.parentElement.getBoundingClientRect();
    const left = rect.left - parentRect.left;
    const width = rect.width;

    pill.style.width = `${width}px`;
    pill.style.transform = `translateX(${left}px)`;
    pill.style.opacity = '1';
}

function slideContent(index) {
    const percentage = index * -20; 
    contentTrack.style.transform = `translateX(${percentage}%)`;
}

window.addEventListener('load', () => {
    const initialActive = document.querySelector('.pill-nav-item.active');
    updatePill(initialActive);
    slideContent(activeIndex);
});

navItems.forEach((item) => {
    item.addEventListener('click', (e) => {
        navItems.forEach(nav => nav.classList.remove('active'));
        e.target.classList.add('active');
        updatePill(e.target);
        const index = parseInt(e.target.dataset.index);
        slideContent(index);
    });
});

window.addEventListener('resize', () => {
    const active = document.querySelector('.pill-nav-item.active');
    updatePill(active);
});