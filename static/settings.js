    // Tab navigation functionality using obfuscated class and id names
    document.addEventListener('DOMContentLoaded', function() {
        const navItems = document.querySelectorAll('.a11');
        const sections = document.querySelectorAll('.a14');
        
        navItems.forEach(item => {
          item.addEventListener('click', function() {
            // Remove obfuscated active class from all tabs
            navItems.forEach(nav => nav.classList.remove('a12'));
            
            // Add active class to clicked tab
            this.classList.add('a12');
            
            // Hide all sections
            sections.forEach(section => section.classList.remove('a12'));
            
            // Show selected section based on data-tab attribute (b1, b2, b3, b4)
            const targetTab = this.getAttribute('data-tab');
            document.getElementById(targetTab).classList.add('a12');
          });
        });
        
        // Set initial letter avatar based on the first character of the obfuscated user-name
        const avatar = document.getElementById('a5');
        const name = document.querySelector('.a8').textContent;
        avatar.textContent = name.charAt(0);
      });
      
      // Obfuscated function to change avatar color (f1)
      function f1(colorClass) {
        const avatar = document.getElementById('a5');
        // Remove all obfuscated avatar color classes
        avatar.classList.remove('a25', 'a26', 'a27', 'a28', 'a29', 'a30');
        // Add the selected color class
        avatar.classList.add(colorClass);
        
        // Update active state in color options
        const colorOptions = document.querySelectorAll('.a24');
        colorOptions.forEach(option => {
          option.classList.remove('a12');
          if (option.classList.contains(colorClass)) {
            option.classList.add('a12');
          }
        });
      }