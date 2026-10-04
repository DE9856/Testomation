// [testomation bug] Seeded-bug toggles for the benchmark (docs/EVALUATION.md).
// BUGS="publish-500,bio-not-saved" turns bugs on; empty = the clean app.
const BUGS = new Set((process.env.BUGS || "").split(",").map((s) => s.trim()).filter(Boolean));
module.exports = { bug: (id) => BUGS.has(id), BUGS };
