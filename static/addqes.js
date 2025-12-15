document.addEventListener('DOMContentLoaded', function() {
    const questionText = document.getElementById('questionText');
    const editorToolbar = document.getElementById('editorToolbar');
    let selectedText = '';
    let selectionStart = 0;
    let selectionEnd = 0;
    let longPressTimer;
    let isTouchDevice = 'ontouchstart' in window;
  
    function showToolbar(x, y) {
    const selectionRange = questionText.getBoundingClientRect();

    const toolbarX = selectionRange.left + (selectionRange.width / 2) - (editorToolbar.offsetWidth / 2);
    const toolbarY = y - editorToolbar.offsetHeight - 10; 

    const maxX = window.innerWidth - editorToolbar.offsetWidth - 10;
    

    editorToolbar.style.left = `${0}px`;
    editorToolbar.style.top = `${toolbarY-170}px`;
    editorToolbar.classList.add('active');
}

    
    // Function to hide toolbar
    function hideToolbar() {
        editorToolbar.classList.remove('active');
    }
    
    // Function to apply formatting
    function applyFormatting(format) {
        let formattedText = '';
        
        switch (format) {
          case 'bold':
              formattedText = `***${selectedText}***`;
              break;
          case 'italic':
              formattedText = `*${selectedText}*`;
              break;
          case 'code':
              formattedText = `\`\`\`${selectedText}\`\`\``; // Formats as a code block
              break;
      }
        // Replace the selected text with formatted text
        const currentValue = questionText.value;
        questionText.value = currentValue.substring(0, selectionStart) + 
                              formattedText + 
                              currentValue.substring(selectionEnd);
        
        // Hide the toolbar
        hideToolbar();
    }
    
    // Event listeners for desktop
    if (!isTouchDevice) {
questionText.addEventListener('mouseup', function (e) {
selectedText = this.value.substring(this.selectionStart, this.selectionEnd);
if (selectedText) {
    selectionStart = this.selectionStart;
    selectionEnd = this.selectionEnd;

    // Get the bounding box of the selected text
    const rect = this.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

    // Calculate a better position for the toolbar
    const toolbarX = rect.left + (rect.width / 2) - (editorToolbar.offsetWidth / 2);
    const toolbarY = rect.top + scrollTop - editorToolbar.offsetHeight - 10;

    showToolbar(toolbarX, toolbarY);
} else {
    hideToolbar();
}
});

    } else {
        // For touch devices - long press implementation
        questionText.addEventListener('touchstart', function(e) {
            longPressTimer = setTimeout(() => {
                // Try to get selected text (this is tricky on mobile)
                selectedText = window.getSelection().toString();
                if (selectedText) {

                    const touch = e.touches[0];
                    showToolbar(touch.clientX, touch.clientY);
                    const fullText = this.value;
                    selectionStart = fullText.indexOf(selectedText);
                    selectionEnd = selectionStart + selectedText.length;
                }
            }, 1); // 500ms long press
        });
        
        questionText.addEventListener('touchend', function() {
            clearTimeout(longPressTimer);
        });
        
        questionText.addEventListener('touchmove', function() {
            clearTimeout(longPressTimer);
        });
    }
    
    // Handle toolbar button clicks
    document.querySelectorAll('.editor-button').forEach(button => {
        button.addEventListener('click', function() {
            const format = this.getAttribute('data-format');
            applyFormatting(format);
        });
    });
    
    // Hide toolbar when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.editor-container') && !e.target.closest('.editor-toolbar')) {
            hideToolbar();
        }
    });
    

});

 