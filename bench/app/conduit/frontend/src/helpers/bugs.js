// [testomation bug] Seeded-bug toggles, injected by the backend as window.__BUGS.
export const bug = (id) => (window.__BUGS || []).includes(id);
