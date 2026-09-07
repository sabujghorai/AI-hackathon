document.addEventListener("DOMContentLoaded", function () {

    const form = document.getElementById("requestForm");

    if (form) {
        form.addEventListener("submit", function (e) {
            e.preventDefault();

            const department = document.getElementById("department").value;
            const section = document.getElementById("section").value;
            const issue = document.getElementById("issue").value;
            const priority = document.getElementById("priority").value;

            // Get existing requests from storage (or empty list if none)
            let requests = JSON.parse(localStorage.getItem("maintenanceRequests")) || [];

            // Add new request
            requests.push({
                day: "New",
                department: department,
                section: section,
                issue: issue,
                priority: priority
            });

            // Save back to storage
            localStorage.setItem("maintenanceRequests", JSON.stringify(requests));

            document.getElementById("confirmMsg").textContent =
                "Request submitted successfully! Check Block Schedule page to see it.";

            form.reset();
        });
    }

    // ---- PART 2: Load Requests into Schedule Table ----
    const scheduleBody = document.getElementById("scheduleBody");

    if (scheduleBody) {
        let requests = JSON.parse(localStorage.getItem("maintenanceRequests")) || [];

        requests.forEach(function (req) {
            const row = document.createElement("tr");

            row.innerHTML = `
                <td>${req.day}</td>
                <td>${req.department}</td>
                <td>${req.section}</td>
                <td>${req.issue}</td>
                <td class="${req.priority.toLowerCase()}">${req.priority}</td>
            `;

            scheduleBody.appendChild(row);
        });
    }
    // ---- PART 3: Update Dashboard Pending Count ----
    const pendingCountEl = document.getElementById("pendingCount");

    if (pendingCountEl) {
        let requests = JSON.parse(localStorage.getItem("maintenanceRequests")) || [];
        pendingCountEl.textContent = requests.length;
    }
});