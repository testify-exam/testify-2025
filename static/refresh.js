document.addEventListener('DOMContentLoaded', function() {
    const refreshButton = document.getElementById('refreshBtn');
    let touchTimeout;
    
    // Make refresh button more visible when user interacts with page
    function showRefreshButton() {
      refreshButton.style.opacity = '0.8';
      
      clearTimeout(touchTimeout);
      touchTimeout = setTimeout(() => {
        refreshButton.style.opacity = '0.3';
      }, 3000);
    }
    
    // Add event listeners for user interaction
    document.addEventListener('touchstart', showRefreshButton);
    document.addEventListener('touchmove', showRefreshButton);
    document.addEventListener('mousemove', showRefreshButton);
    document.addEventListener('click', showRefreshButton);
    
    // Refresh page when button is clicked
    refreshButton.addEventListener('click', function(e) {
      e.preventDefault();
      
      // Animation effect
      refreshButton.style.opacity = '1';
      refreshButton.style.transform = 'rotate(360deg)';
      refreshButton.style.transition = 'transform 0.5s ease, opacity 0.1s ease';
      
      // Reload after animation
      setTimeout(() => {
        window.location.reload();
      }, 500);
    });
    
    // For mobile detection
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    if (isMobile) {
      refreshButton.style.width = '40px';
      refreshButton.style.height = '40px';
    }
  });
