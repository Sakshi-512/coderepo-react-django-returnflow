export function formatDateTime(value) {
    if (!value) return "--";

    return new Date(value).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    });
}

export function formatCurrency(value) {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(value));
}

const WORD_BOUNDARY = /_/g;

export function humanize(value) {
    if (!value) return "";

    return value
        .toString()
        .replace(WORD_BOUNDARY, " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
