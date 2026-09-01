/**
 * A lexer for the JavaScript that a built artifact actually ships, plus the
 * network-target rules the offline bundle gate applies to it.
 *
 * The gate has to answer a question about code, and the code arrives minified
 * and interleaved with deck prose in the same file. Matching text would answer
 * the wrong question in both directions: a sentence that mentions `fetch` is
 * not a request, and a request written across a template literal is not a
 * sentence. Reading the script as tokens keeps comments, string contents and
 * regular expressions out of the answer, and lets a rule name the position a
 * remote address appears in rather than only the address itself.
 *
 * The lexer is deliberately small. It resolves the one genuinely ambiguous
 * character in JavaScript, `/`, with the standard rule that a regular
 * expression may begin only where a value may not continue.
 */

export type JavaScriptTokenKind =
  "identifier" | "numeric" | "punctuation" | "regular-expression" | "text";

export interface JavaScriptToken {
  readonly kind: JavaScriptTokenKind;
  readonly value: string;
}

// Words after which a `/` opens a regular expression rather than dividing.
const REGULAR_EXPRESSION_PRECEDING_WORDS = new Set([
  "await",
  "case",
  "delete",
  "do",
  "else",
  "in",
  "instanceof",
  "new",
  "of",
  "return",
  "throw",
  "typeof",
  "void",
  "yield",
]);

// Punctuation after which a value has just ended, so `/` divides.
const VALUE_CLOSING_PUNCTUATION = new Set([")", "]", "++", "--"]);

// Punctuation after which a `{` opens a block rather than an object literal.
const BLOCK_BRACE_PRECEDING_PUNCTUATION = new Set([")", "]", "}", ";", "=>"]);

// Words after which a `{` opens an object literal rather than a block.
const EXPRESSION_BRACE_PRECEDING_WORDS = new Set([
  "await",
  "case",
  "delete",
  "in",
  "instanceof",
  "of",
  "return",
  "throw",
  "typeof",
  "void",
  "yield",
]);

// Identifier ranges that deliberately exclude every character JavaScript
// treats as whitespace or a format control above ASCII - U+00A0, U+1680,
// U+2000-200A, U+2028, U+2029, U+202F, U+205F, U+3000 and U+FEFF. Folding
// those into a name would glue a separator onto the identifier before it and
// hide the call that follows.
const IDENTIFIER_START =
  /[A-Za-z_$\u00aa\u00b5\u00ba\u00c0-\u02ff\u0370-\u167f\u1681-\u1fff\u200b-\u2027\u202a-\u202e\u2030-\u205e\u2060-\u2fff\u3001-\ud7ff\uf900-\ufdcf\ufdf0-\ufefe\uff00-\ufffd]/;
const IDENTIFIER_PART =
  /[A-Za-z0-9_$\u00aa\u00b5\u00b7\u00ba\u00c0-\u02ff\u0300-\u036f\u0370-\u167f\u1681-\u1fff\u200b-\u2027\u202a-\u202e\u2030-\u205e\u2060-\u2fff\u3001-\ud7ff\uf900-\ufdcf\ufdf0-\ufefe\uff00-\ufffd]/;
const NUMERIC_PART = /[0-9a-fA-FxXoObBnE_.]/;
// Every character JavaScript treats as whitespace or a line terminator,
// including the ones above ASCII that a beacon could hide behind.
const JAVASCRIPT_WHITESPACE =
  /[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]/;

const SIMPLE_ESCAPES = new Map([
  ["n", "\n"],
  ["r", "\r"],
  ["t", "\t"],
  ["b", "\b"],
  ["f", "\f"],
  ["v", "\v"],
  ["0", "\0"],
]);

function decodeEscape(
  source: string,
  index: number,
): { text: string; next: number } {
  const character = source[index];
  if (character === undefined) {
    return { text: "", next: index };
  }
  if (character === "x") {
    const code = Number.parseInt(source.slice(index + 1, index + 3), 16);
    return Number.isNaN(code)
      ? { text: character, next: index + 1 }
      : { text: String.fromCharCode(code), next: index + 3 };
  }
  if (character === "u") {
    if (source[index + 1] === "{") {
      const end = source.indexOf("}", index + 2);
      const code =
        end < 0
          ? Number.NaN
          : Number.parseInt(source.slice(index + 2, end), 16);
      return Number.isNaN(code) || code > 0x10ffff
        ? { text: character, next: index + 1 }
        : { text: String.fromCodePoint(code), next: end + 1 };
    }
    const code = Number.parseInt(source.slice(index + 1, index + 5), 16);
    return Number.isNaN(code)
      ? { text: character, next: index + 1 }
      : { text: String.fromCharCode(code), next: index + 5 };
  }
  return {
    text: SIMPLE_ESCAPES.get(character) ?? character,
    next: index + 1,
  };
}

function readQuoted(
  source: string,
  start: number,
  quote: string,
): { value: string; next: number } {
  let value = "";
  let index = start;
  while (index < source.length) {
    const character = source[index]!;
    if (character === "\\") {
      const decoded = decodeEscape(source, index + 1);
      value += decoded.text;
      index = decoded.next;
      continue;
    }
    if (character === quote) {
      return { value, next: index + 1 };
    }
    value += character;
    index += 1;
  }
  return { value, next: index };
}

function readRegularExpression(source: string, start: number): number {
  let index = start;
  let inClass = false;
  while (index < source.length) {
    const character = source[index]!;
    if (character === "\\") {
      index += 2;
      continue;
    }
    if (character === "[") {
      inClass = true;
    } else if (character === "]") {
      inClass = false;
    } else if (character === "/" && !inClass) {
      index += 1;
      while (index < source.length && IDENTIFIER_PART.test(source[index]!)) {
        index += 1;
      }
      return index;
    } else if (character === "\n") {
      return index;
    }
    index += 1;
  }
  return index;
}

function regularExpressionMayFollow(
  previous: JavaScriptToken | undefined,
  closedExpressionBrace: boolean,
): boolean {
  if (previous === undefined) {
    return true;
  }
  if (previous.kind === "punctuation") {
    // `}` ends a block, after which a regular expression may start, or an
    // object literal, after which `/` divides it.
    if (previous.value === "}") {
      return !closedExpressionBrace;
    }
    return !VALUE_CLOSING_PUNCTUATION.has(previous.value);
  }
  return (
    previous.kind === "identifier" &&
    REGULAR_EXPRESSION_PRECEDING_WORDS.has(previous.value)
  );
}

function opensExpressionBrace(previous: JavaScriptToken | undefined): boolean {
  if (previous === undefined) {
    return false;
  }
  if (previous.kind === "punctuation") {
    return !BLOCK_BRACE_PRECEDING_PUNCTUATION.has(previous.value);
  }
  return (
    previous.kind !== "identifier" ||
    EXPRESSION_BRACE_PRECEDING_WORDS.has(previous.value)
  );
}

/**
 * Read a script into tokens. Comments are dropped; string, template and
 * regular-expression contents are kept as single tokens so their contents can
 * never be mistaken for code. Template substitutions are lexed as code.
 */
export function readJavaScriptTokens(source: string): JavaScriptToken[] {
  const tokens: JavaScriptToken[] = [];
  // Each entry is the brace depth at which an open template resumes.
  const templateDepths: number[] = [];
  // Whether each open `{` began an object literal rather than a block.
  const braceKinds: boolean[] = [];
  let closedExpressionBrace = false;
  let braceDepth = 0;
  let index = 0;

  const readTemplateChunk = (start: number): number => {
    let value = "";
    let cursor = start;
    while (cursor < source.length) {
      const character = source[cursor]!;
      if (character === "\\") {
        const decoded = decodeEscape(source, cursor + 1);
        value += decoded.text;
        cursor = decoded.next;
        continue;
      }
      if (character === "`") {
        tokens.push({ kind: "text", value });
        return cursor + 1;
      }
      if (character === "$" && source[cursor + 1] === "{") {
        tokens.push({ kind: "text", value });
        templateDepths.push(braceDepth);
        braceDepth += 1;
        braceKinds.push(true);
        return cursor + 2;
      }
      value += character;
      cursor += 1;
    }
    tokens.push({ kind: "text", value });
    return cursor;
  };

  while (index < source.length) {
    const character = source[index]!;
    if (JAVASCRIPT_WHITESPACE.test(character)) {
      index += 1;
      continue;
    }
    if (character === "/" && source[index + 1] === "/") {
      const newline = source.indexOf("\n", index);
      index = newline < 0 ? source.length : newline + 1;
      continue;
    }
    if (character === "/" && source[index + 1] === "*") {
      const end = source.indexOf("*/", index + 2);
      index = end < 0 ? source.length : end + 2;
      continue;
    }
    if (character === "/") {
      if (
        regularExpressionMayFollow(
          tokens[tokens.length - 1],
          closedExpressionBrace,
        )
      ) {
        const end = readRegularExpression(source, index + 1);
        tokens.push({
          kind: "regular-expression",
          value: source.slice(index, end),
        });
        index = end;
        continue;
      }
      const operator = source[index + 1] === "=" ? "/=" : "/";
      tokens.push({ kind: "punctuation", value: operator });
      index += operator.length;
      continue;
    }
    if (character === '"' || character === "'") {
      const quoted = readQuoted(source, index + 1, character);
      tokens.push({ kind: "text", value: quoted.value });
      index = quoted.next;
      continue;
    }
    if (character === "`") {
      index = readTemplateChunk(index + 1);
      continue;
    }
    if (character === "{") {
      braceDepth += 1;
      braceKinds.push(opensExpressionBrace(tokens[tokens.length - 1]));
      tokens.push({ kind: "punctuation", value: "{" });
      index += 1;
      continue;
    }
    if (character === "}") {
      braceDepth = Math.max(0, braceDepth - 1);
      closedExpressionBrace = braceKinds.pop() ?? false;
      if (
        templateDepths.length > 0 &&
        templateDepths[templateDepths.length - 1] === braceDepth
      ) {
        templateDepths.pop();
        index = readTemplateChunk(index + 1);
        continue;
      }
      tokens.push({ kind: "punctuation", value: "}" });
      index += 1;
      continue;
    }
    if (
      IDENTIFIER_START.test(character) ||
      (character === "\\" &&
        (source[index + 1] === "u" || source[index + 1] === "x"))
    ) {
      // An identifier may spell any of its characters as an escape, so
      // `\u0057ebSocket` is `WebSocket`. Decode as we read.
      let value = "";
      let end = index;
      while (end < source.length) {
        const next = source[end]!;
        const pattern = value.length === 0 ? IDENTIFIER_START : IDENTIFIER_PART;
        if (
          next === "\\" &&
          (source[end + 1] === "u" || source[end + 1] === "x")
        ) {
          const decoded = decodeEscape(source, end + 1);
          if (
            decoded.next === end + 1 ||
            decoded.text.length === 0 ||
            !pattern.test(decoded.text)
          ) {
            break;
          }
          value += decoded.text;
          end = decoded.next;
          continue;
        }
        if (!pattern.test(next)) {
          break;
        }
        value += next;
        end += 1;
      }
      if (value.length > 0) {
        tokens.push({ kind: "identifier", value });
        index = end;
        continue;
      }
    }
    if (
      /[0-9]/.test(character) ||
      (character === "." && /[0-9]/.test(source[index + 1] ?? ""))
    ) {
      let end = index + 1;
      while (end < source.length && NUMERIC_PART.test(source[end]!)) {
        end += 1;
      }
      tokens.push({ kind: "numeric", value: source.slice(index, end) });
      index = end;
      continue;
    }
    const twoCharacter = source.slice(index, index + 2);
    if (
      twoCharacter === "++" ||
      twoCharacter === "--" ||
      twoCharacter === "=>"
    ) {
      tokens.push({ kind: "punctuation", value: twoCharacter });
      index += 2;
      continue;
    }
    tokens.push({ kind: "punctuation", value: character });
    index += 1;
  }

  return tokens;
}

// Callables that take a request address as an argument.
const NETWORK_CALLEES = new Set([
  "EventSource",
  "WebSocket",
  "XMLHttpRequest",
  "fetch",
  "import",
  "importScripts",
  "open",
  "sendBeacon",
  "setAttribute",
]);

// Names that only exist to reach the network, wherever they appear.
const NETWORK_CAPABILITIES = new Set([
  "EventSource",
  "WebSocket",
  "XMLHttpRequest",
  "importScripts",
  "sendBeacon",
]);

// Names a deck source has no honest reason to use. First-party source is
// small, hand-written and reviewed, so the presence of the name is the
// finding - the shape of its arguments does not have to be worked out.
const FORBIDDEN_SOURCE_CAPABILITIES = new Set([
  "EventSource",
  "WebSocket",
  "XMLHttpRequest",
  "dangerouslySetInnerHTML",
  "fetch",
  "importScripts",
  "sendBeacon",
]);

// Properties whose value is fetched by the browser once assigned.
const URL_PROPERTIES = new Set([
  "action",
  "formaction",
  "href",
  "ping",
  "poster",
  "src",
  "srcset",
]);

// Sinks that parse their argument as markup, where an address can hide inside
// a tag rather than being the whole value.
const MARKUP_PROPERTIES = new Set(["innerHTML", "outerHTML"]);
const MARKUP_CALLEES = new Set(["insertAdjacentHTML", "write", "writeln"]);

const REMOTE_ADDRESS = /^(?:(?:https?|wss?|ftp):)?\/\/[^/\s]/i;
const REMOTE_ADDRESS_ANYWHERE = /(?:https?|wss?|ftp):\/\/[^/\s"'`<>]/i;

function isRemoteAddress(token: JavaScriptToken | undefined): boolean {
  return token?.kind === "text" && REMOTE_ADDRESS.test(token.value.trim());
}

function containsRemoteAddress(token: JavaScriptToken | undefined): boolean {
  return token?.kind === "text" && REMOTE_ADDRESS_ANYWHERE.test(token.value);
}

function literalArgumentsOfCall(
  tokens: readonly JavaScriptToken[],
  openParenthesis: number,
): JavaScriptToken[] {
  const literals: JavaScriptToken[] = [];
  let depth = 0;
  for (let index = openParenthesis; index < tokens.length; index += 1) {
    const token = tokens[index]!;
    if (token.kind === "punctuation") {
      if (token.value === "(") {
        depth += 1;
      } else if (token.value === ")") {
        depth -= 1;
        if (depth === 0) {
          return literals;
        }
      }
      continue;
    }
    if (token.kind === "text") {
      literals.push(token);
    }
  }
  return literals;
}

/**
 * Resolve the name a token refers to.
 *
 * `x.sendBeacon` and `x["sendBeacon"]` name the same thing, and only the first
 * is an identifier token. A string used as a computed member name is treated
 * as the name it spells.
 */
function memberName(
  tokens: readonly JavaScriptToken[],
  index: number,
): { name: string; after: number } | null {
  const token = tokens[index]!;
  if (token.kind === "identifier") {
    return { name: token.value, after: index + 1 };
  }
  if (
    token.kind === "text" &&
    tokens[index - 1]?.value === "[" &&
    tokens[index + 1]?.value === "]"
  ) {
    return { name: token.value, after: index + 2 };
  }
  return null;
}

function networkIssuesAt(
  tokens: readonly JavaScriptToken[],
  index: number,
  capabilities: ReadonlySet<string>,
): string[] {
  const member = memberName(tokens, index);
  if (member === null) {
    return [];
  }
  const { name, after } = member;
  const issues: string[] = [];
  if (capabilities.has(name)) {
    issues.push(`network capability ${name}`);
    return issues;
  }
  const next = tokens[after];
  const called = next?.kind === "punctuation" && next.value === "(";
  if (called && NETWORK_CALLEES.has(name)) {
    for (const literal of literalArgumentsOfCall(tokens, after)) {
      if (isRemoteAddress(literal)) {
        issues.push(
          `remote request ${literal.value.trim()} passed to ${name}()`,
        );
      }
    }
  }
  if (called && MARKUP_CALLEES.has(name)) {
    for (const literal of literalArgumentsOfCall(tokens, after)) {
      if (containsRemoteAddress(literal)) {
        issues.push(`remote request in markup passed to ${name}()`);
      }
    }
  }
  const assigned = next?.kind === "punctuation" && next.value === "=";
  if (assigned && URL_PROPERTIES.has(name.toLocaleLowerCase("en"))) {
    const value = tokens[after + 1];
    if (isRemoteAddress(value)) {
      issues.push(`remote request ${value!.value.trim()} assigned to ${name}`);
    }
  }
  if (assigned && MARKUP_PROPERTIES.has(name)) {
    if (containsRemoteAddress(tokens[after + 1])) {
      issues.push(`remote request in markup assigned to ${name}`);
    }
  }
  return issues;
}

/**
 * Report the network reachable from a built artifact's script: capabilities
 * that exist only to make requests, and remote addresses that sit in a
 * position the browser will request from.
 *
 * A bundled artifact contains third-party code that may call `fetch` for
 * honest local reasons, so a call alone is not the finding here; the address
 * has to be visible. `findSourceCapabilities` is the stricter rule, and is the
 * one that decides first-party source.
 */
export function findNetworkTargets(source: string): string[] {
  const tokens = readJavaScriptTokens(source);
  const issues: string[] = [];
  for (let index = 0; index < tokens.length; index += 1) {
    issues.push(...networkIssuesAt(tokens, index, NETWORK_CAPABILITIES));
  }
  return [...new Set(issues)];
}

/**
 * Report the capabilities a first-party presentation source uses.
 *
 * Reading the source as tokens is what lets deck copy talk about the network:
 * a sentence inside a string literal that mentions `fetch` is text, while a
 * call to `fetch` is a call, whatever its arguments are made of.
 */
export function findSourceCapabilities(source: string): string[] {
  const tokens = readJavaScriptTokens(source);
  const issues: string[] = [];

  for (let index = 0; index < tokens.length; index += 1) {
    issues.push(
      ...networkIssuesAt(tokens, index, FORBIDDEN_SOURCE_CAPABILITIES),
    );
    const token = tokens[index]!;
    if (token.kind !== "identifier") {
      continue;
    }
    const next = tokens[index + 1];
    const called = next?.kind === "punctuation" && next.value === "(";
    if (token.value === "eval" && called) {
      issues.push("eval");
    }
    if (
      token.value === "Function" &&
      tokens[index - 1]?.kind === "identifier" &&
      tokens[index - 1]!.value === "new"
    ) {
      issues.push("Function constructor");
    }
    if (token.value === "from" || token.value === "import") {
      const specifier =
        token.value === "import" && called
          ? tokens[index + 2]
          : tokens[index + 1];
      if (isRemoteAddress(specifier)) {
        issues.push(`remote module import ${specifier!.value.trim()}`);
      }
      if (token.value === "import" && called && specifier?.kind !== "text") {
        // A computed specifier cannot be inventoried, so it cannot be shown
        // to resolve to anything that ships in the bundle.
        issues.push("dynamic import of a computed module specifier");
      }
    }
  }

  return [...new Set(issues)];
}
