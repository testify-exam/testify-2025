async function updateScorePrivacy(attemptId, isPublic) {
    try {
      const formData = new FormData();
      formData.append('attempt_id', attemptId);
      formData.append('is_public', isPublic);
      const response = await fetch('/student/toggle-score-privacy', {
        method: 'POST',
        body: formData,
        credentials: 'include'
      });
      if (!response.ok) {
        console.error('Error updating privacy setting');
        return;
      }
      // If update is successful, update the UI.
      const scoreCell = document.getElementById(`score-${attemptId}`);

    } catch (error) {
      console.error('Error:', error);
    }
  }
  
  // Called when a radio button changes.
  function handleToggle(radioElement, attemptId) {
    const isPublic = radioElement.value;  // "true" or "false"
    updateScorePrivacy(attemptId, isPublic);
  }