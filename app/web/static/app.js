import { boot } from "./js/router.js?v=20260528-sanitize-spaces-v2";

boot().catch((error) => {
  console.error(error);
  const app = document.getElementById("app");
  if (app) {
    app.innerHTML = `
      <div class="screen">
        <main class="content">
          <div class="panel status">Unable to load events. Please try again.</div>
        </main>
      </div>
    `;
  }
});
