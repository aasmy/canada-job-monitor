const test = require("node:test");
const assert = require("node:assert/strict");
const matching = require("../jobmonitor/templates/resume-matching.js");

test("explicit OR and slash alternatives count as one requirement", () => {
  const job = {
    title: "Developer",
    description: "Requirements: JavaScript/TypeScript and Python or Kotlin.",
  };
  const result = matching.score(job, { text: "TypeScript and Python" });
  assert.equal(result.score, 100);
  assert.deepEqual(result.missing, []);
});

test("editing resume text invalidates cached skill evidence", () => {
  const profile = { text: "Python" };
  const job = { title: "Developer", description: "Requirements: Python." };
  assert.equal(matching.score(job, profile).score, 100);
  profile.text = "React";
  assert.equal(matching.score(job, profile).score, 0);
});

test("skill aliases respect word boundaries", () => {
  assert.deepEqual(matching.skills("Node.js"), ["Node.js"]);
  const skills = matching.skills(
    "JavaScript, TypeScript, PostgreSQL, C++, C#, .NET, Node.js, React",
  );
  assert(!skills.includes("Java"));
  assert(!skills.includes("SQL"));
  for (const name of [
    "JavaScript",
    "TypeScript",
    "PostgreSQL",
    "C++",
    "C#",
    ".NET",
    "Node.js",
    "React",
  ])
    assert(skills.includes(name), name);
  assert.deepEqual(matching.skills("We go to project meetings on Monday."), []);
});

test("selecting different resumes changes scores instead of blending the old criteria", () => {
  const job = {
    title: "Backend Developer",
    description:
      "Requirements: Python and PostgreSQL. Preferred skills: Docker.",
    score: 99,
  };
  const backend = matching.score(job, {
    text: "Python PostgreSQL Docker",
    years: null,
  });
  const frontend = matching.score(job, {
    text: "React JavaScript CSS",
    years: null,
  });
  assert.equal(backend.score, 100);
  assert.equal(frontend.score, 0);
  assert.equal(
    matching.score({ ...job, score: 1 }, { text: "Python PostgreSQL Docker" })
      .score,
    100,
  );
  assert.deepEqual(backend.missing, []);
  assert.deepEqual(frontend.missing.sort(), ["PostgreSQL", "Python"]);
});

test("required and preferred categories remain separate", () => {
  const req = matching.requirements({
    title: "Developer",
    description:
      "Requirements: Python and SQL. Nice to have: Docker. Benefits: React to customer feedback.",
  });
  assert.deepEqual(req.required.sort(), ["Python", "SQL"]);
  assert.deepEqual(req.preferred, ["Docker"]);
  assert(!req.required.includes("React"));
});

test("missing listing details do not produce a confident score", () => {
  assert.equal(
    matching.score(
      { title: "Software Engineer", description: "" },
      { text: "Python JavaScript" },
    ).score,
    null,
  );
  assert.equal(
    matching.score(
      { title: "Software Engineer", description: "Preferred skills: Docker." },
      { text: "Docker" },
    ).score,
    null,
  );
});

test("experience is compared only when explicitly provided", () => {
  const job = {
    title: "Developer",
    description: "Requirements: Python. 2 years of professional experience.",
  };
  const unspecified = matching.score(job, { text: "Python", years: null });
  const graduate = matching.score(job, { text: "Python", years: 0 });
  const experienced = matching.score(job, { text: "Python", years: 2 });
  assert.equal(unspecified.breakdown.length, 1);
  assert(graduate.score < experienced.score);
  assert.equal(experienced.score, 100);
});

test("keyword repetition does not boost a resume score", () => {
  const job = {
    title: "Python Developer",
    description: "Requirements: Python and SQL.",
  };
  assert.equal(
    matching.score(job, { text: "Python ".repeat(500) }).score,
    matching.score(job, { text: "Python" }).score,
  );
});

test("unrelated roles and empty profiles are not given invented skill evidence", () => {
  assert.equal(
    matching.score(
      {
        title: "React Developer",
        description: "Requirements: React and JavaScript.",
      },
      { text: "" },
    ).score,
    0,
  );
  assert.equal(matching.score({ title: "React Developer" }, null), null);
});

test("explicitly negated resume experience does not count as a skill", () => {
  assert(
    !matching.skills("No Python experience. React and CSS.").includes("Python"),
  );
});
