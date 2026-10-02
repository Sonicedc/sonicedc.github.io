'use strict';
const copyButton = document.getElementById('copy-url');
copyButton.addEventListener('click', async () => {
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText('https://sonicedc.github.io/');
    status.textContent = 'Repository URL copied. Paste it into Sileo → Sources → +.';
  } catch {
    status.textContent = 'Copy this address: https://sonicedc.github.io/';
  }
});
