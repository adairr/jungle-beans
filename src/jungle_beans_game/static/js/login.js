async function submitAuth(endpoint) {
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;
  const errorBox = document.getElementById("auth-error");
  errorBox.classList.add("hidden");

  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const result = await res.json();
  if (result.ok) {
    window.location.href = "/";
    return;
  }
  errorBox.textContent = result.error || "Something went wrong.";
  errorBox.classList.remove("hidden");
}

document.getElementById("auth-form").addEventListener("submit", (evt) => {
  evt.preventDefault();
  submitAuth("/api/login");
});

document.getElementById("register-btn").addEventListener("click", () => {
  submitAuth("/api/register");
});
