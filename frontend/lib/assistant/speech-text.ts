/**
 * Convert UI text into natural speech text.
 *
 * The visual message can contain compact UI notation, but TTS should not read
 * parenthetical plural markers, raw URLs, markdown or technical punctuation.
 */
export function toSpeechText(input: string): string {
  let text = input;

  // French shorthand markers often used in UI copy.
  text = text
    .replace(/\(s\)/gi, "")
    .replace(/\(e\)/gi, "")
    .replace(/\(es\)/gi, "")
    .replace(/\(x\)/gi, "");

  // Markdown / code decoration should not be spoken literally.
  text = text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1");

  // Avoid reading long technical URLs aloud.
  text = text.replace(
    /\bhttps?:\/\/[^\s]+/gi,
    " lien disponible dans l'interface ",
  );

  // Humanize a few frequent technical separators.
  text = text
    .replace(/→/g, " puis ")
    .replace(/↔/g, " et ")
    .replace(/\s*\/\s*/g, " ou ");

  // Remove repeated punctuation / spacing.
  text = text
    .replace(/[()[\]{}]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();

  return text;
}
