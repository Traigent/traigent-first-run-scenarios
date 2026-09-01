/**
 * A reader for serialized HTML.
 *
 * Both build gates need answers about a document's structure: which elements
 * carry which attribute values, and what a `<script>` or `<style>` block
 * actually contains. Searching the serialized text for a pattern cannot tell
 * those apart from prose, because a text node keeps the quotation marks and
 * angle brackets that an attribute value would have escaped. Reading the
 * markup instead keeps deck copy out of the answer, in both directions: copy
 * that quotes an attribute no longer satisfies a check, and copy that quotes a
 * tag no longer fails one.
 *
 * This is a reader, not a parser: it recovers elements, their attributes, and
 * raw-text content without building a tree. Where a construct is genuinely
 * ambiguous without a full parser - a self-closed raw-text element, which
 * means one thing in HTML and another inside SVG, or a script that enters the
 * escaped script-data states - it refuses the document instead of guessing.
 */

export class HtmlParseError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "HtmlParseError";
  }
}

export interface HtmlElement {
  readonly name: string;
  readonly attributes: ReadonlyMap<string, string>;
}

export interface HtmlRawTextBlock {
  readonly name: string;
  readonly attributes: ReadonlyMap<string, string>;
  readonly content: string;
}

export interface HtmlDocumentContent {
  readonly elements: readonly HtmlElement[];
  readonly rawText: readonly HtmlRawTextBlock[];
}

// Elements whose children are text rather than markup. Their content has to be
// read as an opaque block, and taken to its matching end tag.
const RAW_TEXT_ELEMENTS = new Set([
  "script",
  "style",
  "title",
  "textarea",
  "xmp",
]);

const NAMED_CHARACTER_REFERENCES = new Map([
  ["amp", "&"],
  ["lt", "<"],
  ["gt", ">"],
  ["quot", '"'],
  ["apos", "'"],
  ["nbsp", "\u00a0"],
]);

const REPLACEMENT_CHARACTER = "\ufffd";

export function decodeCharacterReferences(value: string): string {
  return value.replace(
    /&(#[xX][0-9a-fA-F]+|#[0-9]+|[a-zA-Z][a-zA-Z0-9]*);/g,
    (reference: string, body: string) => {
      if (!body.startsWith("#")) {
        return (
          NAMED_CHARACTER_REFERENCES.get(body.toLocaleLowerCase("en")) ??
          reference
        );
      }
      const hexadecimal = body[1] === "x" || body[1] === "X";
      const codePoint = Number.parseInt(
        hexadecimal ? body.slice(2) : body.slice(1),
        hexadecimal ? 16 : 10,
      );
      if (!Number.isSafeInteger(codePoint) || codePoint > 0x10ffff) {
        return reference;
      }
      // Surrogates and the null character are not valid scalar values.
      return codePoint === 0 || (codePoint >= 0xd800 && codePoint <= 0xdfff)
        ? REPLACEMENT_CHARACTER
        : String.fromCodePoint(codePoint);
    },
  );
}

interface StartTag {
  readonly attributes: ReadonlyMap<string, string>;
  readonly selfClosing: boolean;
  readonly end: number;
}

/**
 * Read one start tag's attributes, beginning just after its tag name.
 * Returns `null` when the tag is never terminated.
 */
export function readStartTagAttributes(
  html: string,
  afterTagName: number,
): StartTag | null {
  const whitespaceRun = /\s*/y;
  const attributeName = /[^\s/>=]+/y;
  const unquotedValue = /[^\s>]*/y;
  const skipWhitespace = (index: number): number => {
    whitespaceRun.lastIndex = index;
    whitespaceRun.exec(html);
    return whitespaceRun.lastIndex;
  };

  const attributes = new Map<string, string>();
  let index = afterTagName;
  let solidus = false;
  for (;;) {
    index = skipWhitespace(index);
    if (index >= html.length) {
      return null;
    }
    const character = html[index];
    if (character === ">") {
      return { attributes, selfClosing: solidus, end: index + 1 };
    }
    if (character === "/") {
      solidus = true;
      index += 1;
      continue;
    }
    solidus = false;
    attributeName.lastIndex = index;
    const name = attributeName.exec(html)?.[0];
    if (name === undefined) {
      // A stray "=" where a name belongs: skip it rather than stop reading.
      index += 1;
      continue;
    }
    index = skipWhitespace(attributeName.lastIndex);
    let value = "";
    if (html[index] === "=") {
      index = skipWhitespace(index + 1);
      const quote = html[index];
      if (quote === '"' || quote === "'") {
        const end = html.indexOf(quote, index + 1);
        if (end < 0) {
          return null;
        }
        value = html.slice(index + 1, end);
        index = end + 1;
      } else {
        unquotedValue.lastIndex = index;
        value = unquotedValue.exec(html)?.[0] ?? "";
        index = unquotedValue.lastIndex;
      }
    }
    const attributeKey = name.toLocaleLowerCase("en");
    if (!attributes.has(attributeKey)) {
      attributes.set(attributeKey, decodeCharacterReferences(value));
    }
  }
}

/**
 * Read the attributes of the document element only.
 *
 * A verdict an in-page measurement writes to the root element belongs to that
 * element. Reading its start tag, rather than searching the serialization,
 * means no text node and no other element can answer for it.
 */
export function readDocumentElementAttributes(
  html: string,
): ReadonlyMap<string, string> {
  const whitespaceRun = /\s*/y;
  let index = 0;
  for (;;) {
    whitespaceRun.lastIndex = index;
    whitespaceRun.exec(html);
    index = whitespaceRun.lastIndex;
    if (html.startsWith("<!--", index)) {
      const end = html.indexOf("-->", index + 4);
      if (end < 0) {
        throw new HtmlParseError(
          "HTML has an unterminated comment before the document element",
        );
      }
      index = end + 3;
      continue;
    }
    if (html.startsWith("<!", index) || html.startsWith("<?", index)) {
      const end = html.indexOf(">", index);
      if (end < 0) {
        throw new HtmlParseError(
          "HTML has an unterminated declaration before the document element",
        );
      }
      index = end + 1;
      continue;
    }
    break;
  }
  if (!/^<html(?=[\s/>])/i.test(html.slice(index, index + 6))) {
    throw new HtmlParseError(
      "HTML does not start with an <html> document element",
    );
  }
  const startTag = readStartTagAttributes(html, index + "<html".length);
  if (startTag === null) {
    throw new HtmlParseError(
      "HTML has an unterminated document element start tag",
    );
  }
  return startTag.attributes;
}

/**
 * Find the end tag that closes a raw-text element.
 *
 * The browser ends the block at `</name` followed by whitespace, a solidus or
 * `>`; a longer name such as `</scriptx` does not close it. Matching the name
 * as a bare prefix would end the block early and drop the code after it.
 */
function rawTextEnd(html: string, name: string, from: number): number {
  const closing = new RegExp(`</${name}(?=[\\s/>]|$)`, "gi");
  closing.lastIndex = from;
  return closing.exec(html)?.index ?? -1;
}

/** Read every element and every raw-text block in a serialized document. */
export function readHtml(html: string): HtmlDocumentContent {
  const elements: HtmlElement[] = [];
  const rawText: HtmlRawTextBlock[] = [];
  const tagName = /[a-zA-Z][^\s/>]*/y;
  let index = 0;

  while (index < html.length) {
    const tagStart = html.indexOf("<", index);
    if (tagStart < 0) {
      break;
    }
    index = tagStart;
    if (html.startsWith("<!--", index)) {
      const end = html.indexOf("-->", index + 4);
      index = end < 0 ? html.length : end + 3;
      continue;
    }
    if (
      html.startsWith("<!", index) ||
      html.startsWith("<?", index) ||
      html.startsWith("</", index)
    ) {
      const end = html.indexOf(">", index);
      index = end < 0 ? html.length : end + 1;
      continue;
    }
    tagName.lastIndex = index + 1;
    const name = tagName.exec(html)?.[0]?.toLocaleLowerCase("en");
    if (name === undefined) {
      // A "<" that begins no tag is ordinary text.
      index += 1;
      continue;
    }
    const startTag = readStartTagAttributes(html, tagName.lastIndex);
    if (startTag === null) {
      index += 1;
      continue;
    }
    elements.push({ name, attributes: startTag.attributes });
    index = startTag.end;
    if (!RAW_TEXT_ELEMENTS.has(name)) {
      continue;
    }
    if (startTag.selfClosing) {
      // `<script/>` closes the element in SVG and does not in HTML. Which one
      // applies depends on the element's ancestors, which this reader does not
      // track, and guessing wrong hides everything that follows.
      throw new HtmlParseError(
        `HTML contains a self-closed <${name}/>, whose content boundary depends on the parser's insertion mode`,
      );
    }
    const closing = rawTextEnd(html, name, index);
    const contentEnd = closing < 0 ? html.length : closing;
    const content = html.slice(index, contentEnd);
    if (name === "script" && content.includes("<!--")) {
      // `<!--` inside a script opens the escaped script-data states, where a
      // later `</script>` no longer ends the element.
      throw new HtmlParseError(
        "HTML contains a script that opens the escaped script-data state with `<!--`",
      );
    }
    rawText.push({ name, attributes: startTag.attributes, content });
    index = contentEnd;
  }

  return { elements, rawText };
}
