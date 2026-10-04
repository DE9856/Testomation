// Seeds Conduit through its public API, so data goes through the app's own validation and
// password hashing. Deterministic: same users, articles, tags, comments, follows every time.
// Usage: node seed.mjs [baseUrl]   (default http://localhost:4100)

const base = (process.argv[2] ?? 'http://localhost:4100') + '/api';

async function api(method, path, body, token) {
  const res = await fetch(base + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token && { Authorization: `Token ${token}` }) },
    body: body && JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

export const USERS = [
  { username: 'alice', email: 'alice@conduit.test', password: 'alice-pass-1' },
  { username: 'bob', email: 'bob@conduit.test', password: 'bob-pass-1' },
  { username: 'carol', email: 'carol@conduit.test', password: 'carol-pass-1' },
  { username: 'dave', email: 'dave@conduit.test', password: 'dave-pass-1' },
];

const TOPICS = ['testing', 'playwright', 'react', 'postgres', 'design'];

const tokens = {};
for (const u of USERS) {
  const { user } = await api('POST', '/users', { user: u });
  tokens[u.username] = user.token;
}

// 3 articles per user, 2 tags each → 12 articles, enough for pagination (10 per page)
const slugs = [];
for (const [i, u] of USERS.entries()) {
  for (let n = 1; n <= 3; n++) {
    const { article } = await api('POST', '/articles', {
      article: {
        title: `${u.username[0].toUpperCase() + u.username.slice(1)}'s post ${n}`,
        description: `Post ${n} by ${u.username}`,
        body: `# Heading\n\nBody of post ${n} by **${u.username}**.\n\n- one\n- two`,
        tagList: [TOPICS[(i + n) % TOPICS.length], TOPICS[(i + n + 1) % TOPICS.length]],
      },
    }, tokens[u.username]);
    slugs.push({ slug: article.slug, author: u.username });
  }
}

// alice follows bob and carol; everyone favorites the first article of the next user;
// one comment per article from the next user
for (const name of ['bob', 'carol']) await api('POST', `/profiles/${name}/follow`, null, tokens.alice);
for (const [i, { slug }] of slugs.entries()) {
  const other = USERS[(Math.floor(i / 3) + 1) % USERS.length].username;
  if (i % 3 === 0) await api('POST', `/articles/${slug}/favorite`, null, tokens[other]);
  await api('POST', `/articles/${slug}/comments`, { comment: { body: `Comment from ${other}` } }, tokens[other]);
}

console.log(`seeded ${USERS.length} users, ${slugs.length} articles`);
