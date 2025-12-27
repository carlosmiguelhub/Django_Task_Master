/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    // project-level templates
    "../templates/**/*.html",

    // app templates (core, accounts, etc.)
    "../**/templates/**/*.html",

    // if you keep templates in app folders directly
    "../**/*.html",

    // optional: if you ever use JS with class strings
    "../**/*.js",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
