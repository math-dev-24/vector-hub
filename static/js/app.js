const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

if (csrfToken) {
  document.querySelectorAll('form[method="post"], form[method="POST"]').forEach((form) => {
    if (form.querySelector('input[name="csrf_token"]')) return;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = csrfToken;
    form.prepend(input);
  });
}

const activeJobs = [...document.querySelectorAll('[data-job-id][data-job-active="true"]')];
if (activeJobs.length) {
  const poll = async () => {
    let completed = false;
    await Promise.all(activeJobs.map(async (element) => {
      const response = await fetch(`/api/jobs/${element.dataset.jobId}`);
      if (!response.ok) return;
      const job = await response.json();
      const statusElement = element.querySelector('.job-status') || element;
      statusElement.classList.remove(
        'w-fit', 'rounded-full', 'px-2.5', 'py-1',
        'bg-blue-50', 'bg-emerald-100', 'bg-red-50'
      );
      statusElement.classList.add('block', 'min-w-24');
      const progress = job.progress_total
        ? ` · ${Math.round((job.progress_current / job.progress_total) * 100)} %`
        : '';
      const stage = job.payload?.stage ? ` · ${job.payload.stage}` : '';
      statusElement.textContent = job.status === 'running'
        ? `En cours${stage}${progress}`
        : job.status;
      const percentage = job.progress_total
        ? Math.round((job.progress_current / job.progress_total) * 100)
        : 0;
      let progressTrack = element.querySelector('.progress-track');
      if (!progressTrack && statusElement !== element) {
        progressTrack = document.createElement('div');
        progressTrack.className = 'progress-track';
        progressTrack.setAttribute('role', 'progressbar');
        progressTrack.setAttribute('aria-label', 'Progression du traitement');
        progressTrack.setAttribute('aria-valuemin', '0');
        progressTrack.setAttribute('aria-valuemax', '100');
        progressTrack.innerHTML = '<div class="progress-bar"></div>';
        statusElement.appendChild(progressTrack);
      }
      const progressBar = progressTrack?.querySelector('.progress-bar');
      if (progressBar) progressBar.style.width = `${percentage}%`;
      if (progressTrack) progressTrack.setAttribute('aria-valuenow', String(percentage));
      if (['completed', 'failed', 'cancelled'].includes(job.status)) completed = true;
    }));
    if (completed) window.location.reload();
    else window.setTimeout(poll, 1500);
  };
  window.setTimeout(poll, 1000);
}
