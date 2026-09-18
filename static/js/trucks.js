/**
 * SmartMineGuard - Trucks Fleet Search & Filtering
 */

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("truck-search-input");
  const table = document.getElementById("trucks-table");

  if (searchInput && table) {
    searchInput.addEventListener("input", (e) => {
      const term = e.target.value.toLowerCase().trim();
      const rows = table.querySelectorAll("tbody tr");

      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(term)) {
          row.style.display = "";
        } else {
          row.style.display = "none";
        }
      });
    });
  }

  // Permit table search
  const permitSearch = document.getElementById("permit-search");
  const permitTable = document.getElementById("permits-table");
  if (permitSearch && permitTable) {
    permitSearch.addEventListener("input", (e) => {
      const term = e.target.value.toLowerCase().trim();
      const rows = permitTable.querySelectorAll("tbody tr");

      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(term)) {
          row.style.display = "";
        } else {
          row.style.display = "none";
        }
      });
    });
  }
});
