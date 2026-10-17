/* Deterministic, local-only resume evidence matching. No model or network calls. */
((root) => {
  "use strict";
  const vocabulary = {
    Python: ["python"],
    JavaScript: ["javascript", "js"],
    TypeScript: ["typescript", "ts"],
    Java: ["java"],
    "C#": ["c#", "c sharp"],
    "C++": ["c++"],
    Go: [
      "golang",
      "go programming",
      "go language",
      "go developer",
      "go engineer",
    ],
    Rust: ["rust"],
    Ruby: ["ruby"],
    PHP: ["php"],
    Swift: ["swift"],
    Kotlin: ["kotlin"],
    SQL: ["sql"],
    React: ["react", "react.js", "reactjs"],
    Angular: ["angular", "angularjs"],
    Vue: ["vue", "vue.js", "vuejs"],
    "Next.js": ["next.js", "nextjs"],
    "Node.js": ["node.js", "nodejs"],
    Django: ["django"],
    Flask: ["flask"],
    FastAPI: ["fastapi"],
    ".NET": [".net", "dotnet", "asp.net"],
    Spring: ["spring", "spring boot"],
    Rails: ["ruby on rails", "rails"],
    HTML: ["html", "html5"],
    CSS: ["css", "css3"],
    Tailwind: ["tailwind", "tailwindcss"],
    PostgreSQL: ["postgresql", "postgres"],
    MySQL: ["mysql"],
    MongoDB: ["mongodb", "mongo"],
    Redis: ["redis"],
    GraphQL: ["graphql"],
    REST: ["rest api", "restful", "rest apis"],
    AWS: ["aws", "amazon web services"],
    Azure: ["azure"],
    GCP: ["gcp", "google cloud"],
    Docker: ["docker"],
    Kubernetes: ["kubernetes", "k8s"],
    Terraform: ["terraform"],
    Git: ["git"],
    "GitHub Actions": ["github actions"],
    "CI/CD": ["ci/cd", "ci cd", "continuous integration"],
    Linux: ["linux"],
    Bash: ["bash"],
    PowerShell: ["powershell"],
    Jest: ["jest"],
    Pytest: ["pytest"],
    Playwright: ["playwright"],
    Cypress: ["cypress"],
    Selenium: ["selenium"],
    JUnit: ["junit"],
    Kafka: ["kafka"],
    RabbitMQ: ["rabbitmq"],
    Pandas: ["pandas"],
    NumPy: ["numpy"],
    PyTorch: ["pytorch"],
    TensorFlow: ["tensorflow"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    Spark: ["apache spark", "pyspark"],
    Elasticsearch: ["elasticsearch"],
    Snowflake: ["snowflake"],
    Databricks: ["databricks"],
    "React Native": ["react native"],
    Flutter: ["flutter"],
    Dart: ["dart"],
  };
  const profileCache = new WeakMap();
  const requirementsCache = new WeakMap();
  const escape = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  function hasAlias(text, alias) {
    const boundary = ["js", "ts"].includes(alias) ? "[^a-z0-9.]" : "[^a-z0-9]";
    const expression = new RegExp(
      `(^|${boundary})(${escape(alias)})(?=$|[^a-z0-9])`,
      "gi",
    );
    let match;
    while ((match = expression.exec(text)) !== null) {
      const wordIndex = match.index + match[1].length;
      const preceding = text
        .slice(Math.max(0, wordIndex - 40), wordIndex)
        .split(/[.\n;]/)
        .pop();
      if (
        !/\b(?:no|without|not experienced in|not familiar with)\s+(?:prior\s+)?$/i.test(
          preceding,
        )
      )
        return true;
    }
    return false;
  }
  function skills(text) {
    const result = Object.entries(vocabulary)
      .filter(([, aliases]) =>
        aliases.some((alias) => hasAlias(String(text || ""), alias)),
      )
      .map(([skill]) => skill);
    // A language list may use Go alone; ordinary prose such as "go to" is not evidence.
    if (
      !result.includes("Go") &&
      /(?:^|[,;:\n])\s*Go\s*(?:$|[,;\n])|\b(?:using|in|with|such as)\s+Go\b/.test(
        text || "",
      )
    )
      result.push("Go");
    return result.sort();
  }
  function alternatives(text, names) {
    let groups = names.map((name) => [name]);
    const tokens = [];
    for (const name of names) {
      for (const alias of vocabulary[name]) {
        const boundary = ["js", "ts"].includes(alias)
          ? "[^a-z0-9.]"
          : "[^a-z0-9]";
        const expression = new RegExp(
          `(^|${boundary})(${escape(alias)})(?=$|[^a-z0-9])`,
          "gi",
        );
        for (const match of text.matchAll(expression))
          tokens.push({
            name,
            start: match.index + match[1].length,
            end: match.index + match[0].length,
          });
      }
    }
    tokens.sort((a, b) => a.start - b.start || b.end - a.end);
    for (let index = 1; index < tokens.length; index++) {
      const a = tokens[index - 1],
        b = tokens[index];
      if (
        a.name === b.name ||
        b.start < a.end ||
        !/^\s*(?:or|\/|and\/or)\s*$/i.test(text.slice(a.end, b.start))
      )
        continue;
      const first = groups.find((group) => group.includes(a.name));
      const second = groups.find((group) => group.includes(b.name));
      if (first !== second) {
        first.push(...second);
        groups = groups.filter((group) => group !== second);
      }
    }
    return groups;
  }
  function requirements(job) {
    const text = String(job.description || "");
    const headings =
      /\b(requirements|(?:required|minimum|basic) qualifications|what we look for|what you bring|must.haves?|nice.to.haves?|preferred qualifications|bonus points|preferred skills|preferred(?=:)|benefits|what we offer|about (?:us|the company)|equal opportunity|compensation)\b/gi;
    const groups = {
      required: [],
      preferred: [],
      mentioned: skills(job.title || ""),
    };
    const matches = [...text.matchAll(headings)];
    let from = 0;
    let group = "mentioned";
    for (let i = 0; i <= matches.length; i++) {
      const to = i < matches.length ? matches[i].index : text.length;
      if (group) groups[group].push(...skills(text.slice(from, to)));
      if (i < matches.length) {
        const heading = matches[i][0];
        group = /nice|preferred|bonus/i.test(heading)
          ? "preferred"
          : /benefits|offer|about|opportunity|compensation/i.test(heading)
            ? null
            : "required";
        from = to + heading.length;
      }
    }
    for (const name of Object.keys(groups))
      groups[name] = [...new Set(groups[name])];
    groups.preferred = groups.preferred.filter(
      (skill) => !groups.required.includes(skill),
    );
    groups.mentioned = groups.mentioned.filter(
      (skill) =>
        !groups.required.includes(skill) && !groups.preferred.includes(skill),
    );
    const years = [
      ...text.matchAll(
        /\b(\d{1,2})(?:\s*[-\u2013]\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:(?:professional|relevant|industry|work|commercial|software development)\s+)?experience\b/gi,
      ),
    ]
      .filter(
        (match) =>
          !/preferred|bonus|nice.to.have/i.test(
            text.slice(Math.max(0, match.index - 60), match.index),
          ),
      )
      .map((match) => Number(match[1]));
    groups.years = years.length ? Math.max(...years) : null;
    groups.coreGroups = alternatives(text, [
      ...groups.required,
      ...groups.mentioned,
    ]);
    groups.preferredGroups = alternatives(text, groups.preferred);
    return groups;
  }
  function score(job, resume) {
    if (!resume) return null;
    let profile = profileCache.get(resume);
    if (!profile || profile.text !== resume.text) {
      profile = { text: resume.text, skills: new Set(skills(resume.text)) };
      profileCache.set(resume, profile);
    }
    const owned = profile.skills;
    let cached = requirementsCache.get(job);
    if (
      !cached ||
      cached.description !== job.description ||
      cached.title !== job.title
    ) {
      cached = {
        description: job.description,
        title: job.title,
        value: requirements(job),
      };
      requirementsCache.set(job, cached);
    }
    const req = cached.value;
    const core = [...req.required, ...req.mentioned];
    const covered = req.coreGroups.filter((group) =>
      group.some((skill) => owned.has(skill)),
    );
    const matched = covered.flatMap((group) =>
      group.filter((skill) => owned.has(skill)),
    );
    const missing = req.coreGroups
      .filter((group) => !group.some((skill) => owned.has(skill)))
      .map((group) => group.join(" or "));
    const preferredCovered = req.preferredGroups.filter((group) =>
      group.some((skill) => owned.has(skill)),
    );
    const preferredMatched = preferredCovered.flatMap((group) =>
      group.filter((skill) => owned.has(skill)),
    );
    const preferredMissing = req.preferredGroups
      .filter((group) => !group.some((skill) => owned.has(skill)))
      .map((group) => group.join(" or "));
    const breakdown = [];
    if (core.length)
      breakdown.push({
        label: req.required.length
          ? "Core technical skills"
          : "Skills mentioned in listing",
        weight: 70,
        coverage: covered.length / req.coreGroups.length,
        detail: `${covered.length} of ${req.coreGroups.length} skill requirements covered; explicit alternatives count once`,
      });
    if (req.preferred.length)
      breakdown.push({
        label: "Preferred skills",
        weight: 20,
        coverage: preferredCovered.length / req.preferredGroups.length,
        detail: `${preferredCovered.length} of ${req.preferredGroups.length} preferred skill groups covered`,
      });
    const profileYears =
      resume.years === null || resume.years === "" || resume.years === undefined
        ? null
        : Number(resume.years);
    const experienceKnown =
      Number.isFinite(profileYears) && profileYears >= 0 && req.years !== null;
    if (experienceKnown)
      breakdown.push({
        label: "Stated experience",
        weight: 10,
        coverage: req.years === 0 ? 1 : Math.min(1, profileYears / req.years),
        detail: `Listing: ${req.years}+ years; your profile: ${profileYears} years`,
      });
    const weight = breakdown.reduce((sum, item) => sum + item.weight, 0);
    // Preferred-only evidence cannot establish a meaningful overall technical match.
    const value = core.length
      ? Math.round(
          (100 *
            breakdown.reduce(
              (sum, item) => sum + item.weight * item.coverage,
              0,
            )) /
            weight,
        )
      : null;
    return {
      score: value,
      matched,
      missing,
      required: req.required,
      preferredMatched,
      preferredMissing,
      breakdown,
      experience: experienceKnown
        ? `${profileYears} years in your profile / ${req.years}+ in listing`
        : req.years === null
          ? "Experience requirement not stated"
          : "Add professional years to compare experience",
      evidence:
        value === null
          ? "Not enough technical detail to score"
          : `Based on ${req.coreGroups.length} detected technical skill groups`,
    };
  }
  const api = { skills, requirements, score };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ResumeMatching = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
