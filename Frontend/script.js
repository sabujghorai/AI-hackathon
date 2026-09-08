const state = {
  requests: []
};

const navButtons = document.querySelectorAll('.nav-btn');
const views = document.querySelectorAll('.view');

navButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    navButtons.forEach(b => b.classList.remove('active'));
    views.forEach(v => v.classList.remove('active'));

    btn.classList.add('active');
    document.getElementById(btn.dataset.view).classList.add('active');
  });
});

function updateDashboard() {
  document.getElementById('pendingCount').textContent = state.requests.length;
}

const requestForm = document.getElementById('requestForm');
const confirmMsg = document.getElementById('confirmMsg');
const scheduleBody = document.getElementById('scheduleBody');

const priorityClass = { High: 'high', Medium: 'medium', Low: 'low' };
const dayCycle = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

requestForm.addEventListener('submit', function (e) {
  e.preventDefault();

  const department = document.getElementById('department').value;
  const section = document.getElementById('section').value.trim();
  const issue = document.getElementById('issue').value.trim();
  const priority = document.getElementById('priority').value;

  if (!department || !section || !issue || !priority) return;

  state.requests.push({ department, section, issue, priority });
  updateDashboard();

  const day = dayCycle[state.requests.length % dayCycle.length];
  const row = document.createElement('tr');
  row.innerHTML = `
    <td>${day}</td>
    <td>${department}</td>
    <td>${section}</td>
    <td>TBD</td>
    <td class="${priorityClass[priority]}">${priority}</td>
  `;
  scheduleBody.appendChild(row);

  confirmMsg.textContent = `Request for ${section} (${department}) submitted successfully.`;
  requestForm.reset();

  setTimeout(() => { confirmMsg.textContent = ''; }, 4000);
});

updateDashboard();