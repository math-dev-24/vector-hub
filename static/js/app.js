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
      const progress = job.progress_total
        ? ` · ${job.progress_current}/${job.progress_total}`
        : '';
      const stage = job.payload?.stage ? ` · ${job.payload.stage}` : '';
      statusElement.textContent = job.status === 'running'
        ? `En cours${stage}${progress}`
        : job.status;
      if (['completed', 'failed', 'cancelled'].includes(job.status)) completed = true;
    }));
    if (completed) window.location.reload();
    else window.setTimeout(poll, 1500);
  };
  window.setTimeout(poll, 1000);
}
