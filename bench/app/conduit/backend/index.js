require("dotenv").config();
const env = process.env.NODE_ENV || "development";
const PORT = process.env.PORT || 3001;
const express = require("express");
const cors = require("cors");
const { sequelize } = require("./models");
const errorHandler = require("./middleware/errorHandler");

const usersRoutes = require("./routes/users");
const userRoutes = require("./routes/user");
const articlesRoutes = require("./routes/articles");
const profilesRoutes = require("./routes/profiles");
const tagsRoutes = require("./routes/tags");

const app = express();
app.use(cors());
app.use(express.json());

(async () => {
  try {
    await sequelize.sync({ alter: true });
    console.log(`Connection with ${env} database has been established.`);
  } catch (error) {
    console.error("Unable to connect to the database:", error);
  }
})();

if (process.env.NODE_ENV === "production") {
  // [testomation bug] expose seeded-bug toggles to the frontend as window.__BUGS
  const fs = require("fs");
  const { BUGS } = require("./helper/bugs");
  const indexHtml = () =>
    fs.readFileSync("../frontend/dist/index.html", "utf8").replace(
      "<head>",
      `<head><script>window.__BUGS=${JSON.stringify([...BUGS])}</script>`,
    );
  app.get(["/", "/index.html"], (req, res) => res.type("html").send(indexHtml()));
  // [testomation bug] flaky-slow-articles: ~40% of article-list requests take 6 s
  app.use("/api/articles", (req, res, next) =>
    BUGS.has("flaky-slow-articles") && req.method === "GET" && Math.random() < 0.4
      ? setTimeout(next, 6000)
      : next(),
  );
  app.use(express.static("../frontend/dist"));
  // [testomation patch] SPA fallback: client-side routes like /login load index.html
  app.get(/^\/(?!api\/).*/, (req, res) =>
    res.type("html").send(indexHtml()),
  );
} else {
  app.get("/", (req, res) => res.json({ status: "API is running on /api" }));
}
app.use("/api/users", usersRoutes);
app.use("/api/user", userRoutes);
app.use("/api/articles", articlesRoutes);
app.use("/api/profiles", profilesRoutes);
app.use("/api/tags", tagsRoutes);
app.get("/*any", (req, res) =>
  res.status(404).json({ errors: { body: ["Not found"] } }),
);
app.use(errorHandler);

app.listen(PORT, () =>
  console.log(`Server running on http://localhost:${PORT}`),
);
