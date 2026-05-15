/** Validates rules.yaml examples / negativeExamples against pattern + excludePattern. */

export function selftestRules(rules) {
  const fails = []
  for (const r of rules) {
    if (!r.pattern) {
      fails.push({ rule: r.name, kind: "no-pattern" })
      continue
    }
    let re
    try {
      re = new RegExp(r.pattern, "i")
    } catch (e) {
      fails.push({ rule: r.name, kind: "bad-pattern", error: e.message })
      continue
    }
    let ex
    if (r.excludePattern) {
      try {
        ex = new RegExp(r.excludePattern, "i")
      } catch (e) {
        fails.push({ rule: r.name, kind: "bad-excludePattern", error: e.message })
      }
    }
    for (const sample of r.examples || []) {
      const s = typeof sample === "string" ? sample : sample?.value
      if (s == null) continue
      if (!re.test(s)) fails.push({ rule: r.name, kind: "positive-miss", sample: s })
      else if (ex && ex.test(s)) fails.push({ rule: r.name, kind: "exclude-hides-positive", sample: s })
    }
    for (const sample of r.negativeExamples || []) {
      const w = typeof sample === "string" ? sample : sample?.value
      if (w == null) continue
      if (re.test(w) && !(ex && ex.test(w))) {
        fails.push({ rule: r.name, kind: "negative-hit", sample: w })
      }
    }
  }
  return fails
}
