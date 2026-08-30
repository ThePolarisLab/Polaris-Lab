export const money = (value, currency = "CAD") => {
  if (value === null || value === undefined) return "—";

  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat("en-CA", { style: "currency", currency, maximumFractionDigits: 0 }).format(numeric)
    : "Not available";
};

export const moneyExact = (value, currency = "CAD") => {
  if (value === null || value === undefined) return "—";

  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat("en-CA", {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric)
    : "Not available";
};
