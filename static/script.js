const $ = selector =>
  document.querySelector(selector);

const $$ = selector =>
  [...document.querySelectorAll(selector)];


let posts = [];
let returnFocus = null;
let editorDirty = false;
let editorAuthenticated = false;
let macOSOnly = true;
let autosaveTimer = null;


const SITE_TITLE =
  "Unfuck AI";

const DRAFT_KEY =
  "IKEWL-WAHAS-AJKAD-WAKLL";


const escapeHTML = (
  value = ""
) =>
  String(value).replace(
    /[&<>"']/g,
    character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    })[character]
  );


const slugify = (
  value = ""
) =>
  String(value)
    .toLowerCase()
    .trim()
    .replace(
      /[^a-z0-9]+/g,
      "-"
    )
    .replace(
      /^-+|-+$/g,
      ""
    );


function formatDate(
  value = ""
) {

  if (!value) {
    return "";
  }


  const date =
    new Date(
      `${value}T00:00:00`
    );


  if (
    Number.isNaN(
      date.getTime()
    )
  ) {
    return value;
  }


  return date.toLocaleDateString(
    "en-GB",
    {
      day: "numeric",
      month: "short",
      year: "numeric"
    }
  );

}


function inlineMarkdown(
  text = ""
) {

  return escapeHTML(text)

    .replace(
      /`([^`]+)`/g,
      "<code>$1</code>"
    )

    .replace(
      /\*\*([^*]+)\*\*/g,
      "<strong>$1</strong>"
    )

    .replace(
      /\*([^*]+)\*/g,
      "<em>$1</em>"
    )

    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

}


function renderMarkdown(
  source = ""
) {

  const lines =
    String(source)
      .replace(/\r/g, "")
      .split("\n");


  let html = "";
  let paragraph = [];
  let listType = "";
  let inCode = false;
  let codeLines = [];


  const flushParagraph =
    () => {

      if (
        !paragraph.length
      ) {
        return;
      }


      html +=
        `<p>${inlineMarkdown(
          paragraph.join(" ")
        )}</p>`;


      paragraph = [];

    };


  const closeList =
    () => {

      if (!listType) {
        return;
      }


      html +=
        `</${listType}>`;


      listType = "";

    };


  for (
    const line
    of lines
  ) {

    if (
      line.startsWith(
        "```"
      )
    ) {

      flushParagraph();

      closeList();


      if (inCode) {

        html +=
          `<pre><code>${escapeHTML(
            codeLines.join("\n")
          )}</code></pre>`;


        codeLines = [];

      }


      inCode =
        !inCode;


      continue;

    }


    if (inCode) {

      codeLines.push(
        line
      );

      continue;

    }


    if (
      !line.trim()
    ) {

      flushParagraph();

      closeList();

      continue;

    }


    const heading =
      line.match(
        /^(#{1,3})\s+(.+)/
      );


    if (heading) {

      flushParagraph();

      closeList();


      const level =
        heading[1].length;


      html +=
        `<h${level}>${inlineMarkdown(
          heading[2]
        )}</h${level}>`;


      continue;

    }


    if (
      /^---+$/.test(
        line.trim()
      )
    ) {

      flushParagraph();

      closeList();

      html += "<hr>";

      continue;

    }


    if (
      line.startsWith(
        "> "
      )
    ) {

      flushParagraph();

      closeList();


      html +=
        `<blockquote>${inlineMarkdown(
          line.slice(2)
        )}</blockquote>`;


      continue;

    }


    const unordered =
      line.match(
        /^[-*]\s+(.+)/
      );


    const ordered =
      line.match(
        /^\d+\.\s+(.+)/
      );


    if (
      unordered ||
      ordered
    ) {

      flushParagraph();


      const type =
        unordered
          ? "ul"
          : "ol";


      if (
        listType !==
        type
      ) {

        closeList();

        html +=
          `<${type}>`;

        listType =
          type;

      }


      html +=
        `<li>${inlineMarkdown(
          (
            unordered ||
            ordered
          )[1]
        )}</li>`;


      continue;

    }


    paragraph.push(
      line.trim()
    );

  }


  flushParagraph();

  closeList();


  if (inCode) {

    html +=
      `<pre><code>${escapeHTML(
        codeLines.join("\n")
      )}</code></pre>`;

  }


  return html;

}


function openOverlay(
  id,
  trigger =
    document.activeElement
) {

  const overlay =
    document.getElementById(
      id
    );


  if (!overlay) {
    return;
  }


  returnFocus =
    trigger;


  $$(".overlay.open")
    .forEach(item => {

      if (
        item.id !== id
      ) {

        item.classList.remove(
          "open"
        );

        item.setAttribute(
          "aria-hidden",
          "true"
        );

      }

    });


  overlay.classList.add(
    "open"
  );


  overlay.setAttribute(
    "aria-hidden",
    "false"
  );


  document.body.classList.add(
    "modal-open"
  );


  if (
    id ===
    "reader-overlay"
  ) {

    $$("[data-open-reader]")
      .forEach(button => {

        button.setAttribute(
          "aria-expanded",
          "true"
        );

      });

  }


  setTimeout(
    () => {

      overlay
        .querySelector(
          "input,textarea,button"
        )
        ?.focus();

    },
    30
  );

}


async function closeOverlay(id) {

  const overlay =
    document.getElementById(
      id
    );


  if (!overlay) {
    return;
  }


  if (
    id ===
    "editor-overlay"
  ) {

    clearTimeout(
      autosaveTimer
    );


    saveDraft();


    await logoutWriter();

  }


  overlay.classList.remove(
    "open"
  );


  overlay.setAttribute(
    "aria-hidden",
    "true"
  );


  if (
    id ===
    "reader-overlay"
  ) {

    $$("[data-open-reader]")
      .forEach(button => {

        button.setAttribute(
          "aria-expanded",
          "false"
        );

      });


    if (
      location.hash.startsWith(
        "#read="
      )
    ) {

      history.replaceState(
        null,
        "",
        location.pathname +
        location.search
      );

    }


    document.title =
      SITE_TITLE;

  }


  if (
    !$(".overlay.open")
  ) {

    document.body.classList.remove(
      "modal-open"
    );

  }


  returnFocus
    ?.focus
    ?.();

}


function bindCloseButtons() {

  $$("[data-close]")
    .forEach(button => {

      button.addEventListener(
        "click",
        event => {

          event.preventDefault();


          closeOverlay(
            button.dataset.close
          );

        }
      );

    });

}


document.addEventListener(
  "keydown",
  event => {

    const open =
      $$(".overlay.open")
        .at(-1);


    if (!open) {
      return;
    }


    if (
      event.key ===
      "Escape"
    ) {

      closeOverlay(
        open.id
      );

      return;

    }


    if (
      event.key !==
      "Tab"
    ) {
      return;
    }


    const focusable =
      $$(
        "button:not([disabled])," +
        "input:not([disabled])," +
        "textarea:not([disabled])," +
        "a[href]"
      )
        .filter(
          element =>
            open.contains(
              element
            ) &&
            element.offsetParent !==
              null
        );


    if (!focusable.length) {
      return;
    }


    const first =
      focusable[0];


    const last =
      focusable.at(-1);


    if (
      event.shiftKey &&
      document.activeElement ===
        first
    ) {

      event.preventDefault();

      last.focus();

    }

    else if (
      !event.shiftKey &&
      document.activeElement ===
        last
    ) {

      event.preventDefault();

      first.focus();

    }

  }
);


window.addEventListener(
  "scroll",
  () => {

    $(".nav")
      ?.classList
      .toggle(
        "scrolled",
        scrollY > 40
      );

  },
  {
    passive: true
  }
);


async function loadPublicConfig() {

  try {

    const response =
      await fetch(
        "/api/config",
        {
          cache: "no-store",
          credentials:
            "same-origin"
        }
      );


    if (!response.ok) {

      throw new Error(
        "Could not load configuration."
      );

    }


    const config =
      await response.json();


    macOSOnly =
      config.macosOnly ===
      true;

  }

  catch (error) {

    console.error(
      "Config load failed:",
      error
    );


    macOSOnly =
      true;

  }

}


async function getPosts() {

  const response =
    await fetch(
      "/api/posts",
      {
        cache:
          "no-store",

        credentials:
          "same-origin"
      }
    );


  if (!response.ok) {

    throw new Error(
      "Could not load writing."
    );

  }


  const result =
    await response.json();


  if (
    !result.ok ||
    !Array.isArray(
      result.posts
    )
  ) {

    throw new Error(
      "Invalid writing response."
    );

  }


  posts =
    result.posts
      .filter(
        post =>
          post &&
          typeof post ===
            "object"
      )
      .sort(
        (a, b) =>
          String(
            b.date || ""
          )
          .localeCompare(
            String(
              a.date || ""
            )
          )
      );


  return posts;

}


function renderPostList() {

  const list =
    $("#post-list");


  const count =
    $("#post-count");


  if (count) {

    count.textContent =
      `${posts.length} ${
        posts.length === 1
          ? "post"
          : "posts"
      }`;

  }


  if (!list) {
    return;
  }


  if (!posts.length) {

    list.innerHTML =
      '<div class="loading-card">' +
      "Nothing published yet." +
      "</div>";


    return;

  }


  list.innerHTML =
    "";


  posts.forEach(
    post => {

      const button =
        document.createElement(
          "button"
        );


      button.className =
        "post-item";


      button.type =
        "button";


      button.dataset.file =
        post.file || "";


      const readableDate =
        formatDate(
          post.date || ""
        );


      button.innerHTML = `
        <strong>
          ${escapeHTML(
            post.title ||
            "Untitled"
          )}
        </strong>

        <small>
          <span>
            ${escapeHTML(
              post.author ||
              "Unfuck AI"
            )}
          </span>

          ${
            readableDate
              ? `
                <span>·</span>
                <span>
                  ${escapeHTML(
                    readableDate
                  )}
                </span>
              `
              : ""
          }
        </small>
      `;


      button.addEventListener(
        "click",
        () => {

          openPost(
            post,
            true
          );

        }
      );


      list.append(
        button
      );

    }
  );

}


async function loadPosts() {

  try {

    await getPosts();

    renderPostList();

  }

  catch (error) {

    console.error(
      "Writing load failed:",
      error
    );


    const list =
      $("#post-list");


    if (list) {

      list.innerHTML =
        '<div class="loading-card">' +
        "Writing is unavailable right now." +
        "</div>";

    }

  }

}


async function openPost(
  post,
  updateHash = true
) {

  const article =
    $("#article");


  if (!article) {
    return;
  }


  $$(".post-item")
    .forEach(item => {

      item.classList.toggle(
        "active",
        item.dataset.file ===
          post.file
      );

    });


  article.innerHTML =
    '<div class="empty-state">' +
    "Opening article…" +
    "</div>";


  try {

    const response =
      await fetch(
        `/posts/${encodeURIComponent(
          post.file
        )}`,
        {
          cache:
            "no-store"
        }
      );


    if (!response.ok) {

      throw new Error(
        "Could not load post."
      );

    }


    const markdown =
      await response.text();


    article.innerHTML = `
      <h1 class="article-title">
        ${escapeHTML(
          post.title ||
          "Untitled"
        )}
      </h1>

      <div class="article-meta">

        <span>
          ${escapeHTML(
            post.author ||
            "Unfuck AI"
          )}
        </span>

        <span>
          ${escapeHTML(
            formatDate(
              post.date ||
              ""
            )
          )}
        </span>

      </div>

      <div class="prose">
        ${renderMarkdown(
          markdown
        )}
      </div>
    `;


    document.title =
      `${post.title ||
        "Untitled"} — ${SITE_TITLE}`;


    if (updateHash) {

      history.pushState(
        null,
        "",
        `#read=${encodeURIComponent(
          post.file
        )}`
      );

    }


    $(".article-panel")
      ?.scrollTo({
        top: 0,
        behavior:
          "smooth"
      });

  }

  catch (error) {

    console.error(
      "Post load failed:",
      error
    );


    article.innerHTML =
      '<div class="empty-state">' +
      "This article failed to load." +
      "</div>";

  }

}


async function openReader(
  trigger =
    document.activeElement
) {

  openOverlay(
    "reader-overlay",
    trigger
  );


  if (!posts.length) {

    await loadPosts();

  }


  if (posts.length) {

    const active =
      $(".post-item.active");


    if (!active) {

      await openPost(
        posts[0],
        false
      );

    }

  }

}


function bindReaderButtons() {

  $$("[data-open-reader]")
    .forEach(button => {

      button.addEventListener(
        "click",
        event => {

          event.preventDefault();

          event.stopPropagation();


          openReader(
            event.currentTarget
          );

        }
      );

    });

}


function appearsToBeMac() {

  const platform =
    (
      navigator
        .userAgentData
        ?.platform ||

      navigator.platform ||

      navigator.userAgent ||

      ""
    )
      .toLowerCase();


  return (
    platform.includes(
      "mac"
    ) ||
    platform.includes(
      "macintosh"
    )
  );

}


async function checkAuthentication() {

  try {

    const response =
      await fetch(
        "/api/auth/status",
        {
          credentials:
            "same-origin",

          cache:
            "no-store"
        }
      );


    if (!response.ok) {
      return false;
    }


    const result =
      await response.json();


    return (
      result.authenticated ===
      true
    );

  }

  catch {

    return false;

  }

}


async function logoutWriter() {

  editorAuthenticated =
    false;


  try {

    await fetch(
      "/api/logout",
      {
        method:
          "POST",

        credentials:
          "same-origin",

        cache:
          "no-store"
      }
    );

  }

  catch (error) {

    console.error(
      "Writer logout failed:",
      error
    );

  }

}


async function startWriting(
  trigger =
    document.activeElement
) {

  if (
    macOSOnly &&
    !appearsToBeMac()
  ) {

    alert(
      "Writing access is limited to macOS."
    );

    return;

  }


  if (trigger) {

    trigger.disabled =
      true;

  }


  try {

    await logoutWriter();


    const input =
      $("#auth-phrase");


    const status =
      $("#auth-status");


    if (input) {
      input.value = "";
    }


    if (status) {
      status.textContent = "";
    }


    openOverlay(
      "auth-overlay",
      trigger
    );

  }

  finally {

    if (trigger) {

      trigger.disabled =
        false;

    }

  }

}


function bindWriteButtons() {

  const buttons =
    new Set([
      ...$$(
        "[data-open-write]"
      ),
      ...$$(
        "#open-write"
      )
    ]);


  buttons.forEach(
    button => {

      button.addEventListener(
        "click",
        event => {

          event.preventDefault();

          event.stopPropagation();


          startWriting(
            event.currentTarget
          );

        }
      );

    }
  );

}


async function handleAuthentication(
  event
) {

  event.preventDefault();


  const form =
    event.currentTarget;


  const input =
    $("#auth-phrase");


  const status =
    $("#auth-status");


  const button =
    form.querySelector(
      'button[type="submit"]'
    );


  const phrase =
    input
      ?.value
      .trim() ||
    "";


  if (!phrase) {

    if (status) {

      status.textContent =
        "Enter the publishing phrase.";

    }


    return;

  }


  if (status) {

    status.textContent =
      "Checking…";

  }


  if (button) {

    button.disabled =
      true;

  }


  try {

    await logoutWriter();


    const response =
      await fetch(
        "/api/auth",
        {
          method:
            "POST",

          credentials:
            "same-origin",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify({
              phrase,

              device: {

                platform:
                  navigator
                    .userAgentData
                    ?.platform ||

                  navigator.platform ||

                  "",

                userAgent:
                  navigator.userAgent ||
                  ""

              }

            })
        }
      );


    let result;


    try {

      result =
        await response.json();

    }

    catch {

      throw new Error(
        `Authentication returned HTTP ${response.status}.`
      );

    }


    if (
      !response.ok ||
      !result.ok
    ) {

      throw new Error(
        result?.error ||
        "Access denied."
      );

    }


    const authenticated =
      await checkAuthentication();


    if (!authenticated) {

      throw new Error(
        "Authentication session was not created."
      );

    }


    editorAuthenticated =
      true;


    if (input) {
      input.value = "";
    }


    if (status) {
      status.textContent = "";
    }


    await openEditor();

  }

  catch (error) {

    editorAuthenticated =
      false;


    console.error(
      "Authentication failed:",
      error
    );


    if (status) {

      status.textContent =
        error.message ||
        "Authentication failed.";

    }

  }

  finally {

    if (button) {

      button.disabled =
        false;

    }

  }

}


const markdownEditor =
  $("#markdown-editor");


const editorPreview =
  $("#editor-preview");


const editorFields = [
  "#editor-title",
  "#editor-author",
  "#editor-date",
  "#editor-file",
  "#markdown-editor"
];


function readDraft() {

  try {

    return JSON.parse(
      localStorage.getItem(
        DRAFT_KEY
      ) ||
      "null"
    );

  }

  catch {

    return null;

  }

}


function saveDraft() {

  const draft =
    Object.fromEntries(
      editorFields.map(
        selector => [
          selector,
          $(selector)
            ?.value ||
          ""
        ]
      )
    );


  try {

    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify(
        draft
      )
    );

  }

  catch (error) {

    console.error(
      "Draft save failed:",
      error
    );

    return;

  }


  editorDirty =
    Object.values(
      draft
    )
      .some(
        value =>
          String(value)
            .trim()
      );


  const state =
    $("#save-state");


  if (state) {

    state.textContent =
      editorDirty
        ? "Saved locally"
        : "Draft";

  }

}


function scheduleAutosave() {

  const state =
    $("#save-state");


  if (state) {

    state.textContent =
      "Saving…";

  }


  clearTimeout(
    autosaveTimer
  );


  autosaveTimer =
    setTimeout(
      () => {

        saveDraft();

      },
      500
    );

}


function restoreDraft() {

  const draft =
    readDraft();


  if (!draft) {
    return;
  }


  editorFields.forEach(
    selector => {

      const element =
        $(selector);


      if (!element) {
        return;
      }


      const value =
        draft[selector];


      if (
        typeof value !==
        "string"
      ) {
        return;
      }


      if (!element.value) {

        element.value =
          value;

      }

    }
  );


  editorDirty =
    Object.values(
      draft
    )
      .some(
        value =>
          String(value)
            .trim()
      );


  if (editorDirty) {

    const state =
      $("#save-state");


    if (state) {

      state.textContent =
        "Saved locally";

    }

  }

}


function clearDraft() {

  clearTimeout(
    autosaveTimer
  );


  try {

    localStorage.removeItem(
      DRAFT_KEY
    );

  }

  catch {
  }


  editorDirty =
    false;

}


function clearEditor() {

  editorFields.forEach(
    selector => {

      const element =
        $(selector);


      if (element) {

        element.value =
          "";

      }

    }
  );


  const file =
    $("#editor-file");


  if (file) {

    delete file.dataset.manual;

  }


  const state =
    $("#save-state");


  if (state) {

    state.textContent =
      "Draft";

  }


  updatePreview();

}


function updatePreview() {

  const markdown =
    markdownEditor
      ?.value ||
    "";


  if (!editorPreview) {
    return;
  }


  editorPreview.innerHTML =
    markdown.trim()

      ? renderMarkdown(
          markdown
        )

      : "<p>Preview will appear here.</p>";

}


function bindAutosave() {

  editorFields.forEach(
    selector => {

      $(selector)
        ?.addEventListener(
          "input",
          () => {

            updatePreview();

            scheduleAutosave();

          }
        );

    }
  );

}


async function openEditor() {

  const authenticated =
    await checkAuthentication();


  if (!authenticated) {

    editorAuthenticated =
      false;


    openOverlay(
      "auth-overlay",
      $("#open-write")
    );


    return;

  }


  editorAuthenticated =
    true;


  openOverlay(
    "editor-overlay",
    $("#open-write")
  );


  restoreDraft();


  const date =
    $("#editor-date");


  if (
    date &&
    !date.value
  ) {

    const now =
      new Date();


    const localDate =
      new Date(
        now.getTime() -
        (
          now.getTimezoneOffset() *
          60000
        )
      );


    date.value =
      localDate
        .toISOString()
        .slice(
          0,
          10
        );

  }


  updatePreview();


  setTimeout(
    () => {

      $("#editor-title")
        ?.focus();

    },
    40
  );

}


function bindAutomaticFilename() {

  const title =
    $("#editor-title");


  const file =
    $("#editor-file");


  title
    ?.addEventListener(
      "input",
      event => {

        if (!file) {
          return;
        }


        if (
          file.dataset.manual ===
          "true"
        ) {
          return;
        }


        const slug =
          slugify(
            event.target.value
          );


        file.value =
          slug
            ? `${slug}.md`
            : "";


        scheduleAutosave();

      }
    );


  file
    ?.addEventListener(
      "input",
      event => {

        event.target.dataset.manual =
          "true";

      }
    );

}


function showPublishStatus(
  message,
  timeout = 3000
) {

  const element =
    $("#publish-status");


  if (!element) {
    return;
  }


  element.textContent =
    message;


  element.classList.add(
    "visible"
  );


  clearTimeout(
    showPublishStatus.timer
  );


  if (timeout > 0) {

    showPublishStatus.timer =
      setTimeout(
        () => {

          element.classList.remove(
            "visible"
          );

        },
        timeout
      );

  }

}


async function handlePublish(
  event
) {

  event.preventDefault();


  const button =
    event.currentTarget;


  const authenticated =
    await checkAuthentication();


  if (!authenticated) {

    openOverlay(
      "auth-overlay",
      button
    );


    return;

  }


  clearTimeout(
    autosaveTimer
  );


  saveDraft();


  const title =
    $("#editor-title")
      ?.value
      .trim() ||
    "";


  const author =
    $("#editor-author")
      ?.value
      .trim() ||
    "";


  const date =
    $("#editor-date")
      ?.value
      .trim() ||
    "";


  const file =
    $("#editor-file")
      ?.value
      .trim() ||
    "";


  const markdown =
    markdownEditor
      ?.value
      .trim() ||
    "";


  if (!title) {

    showPublishStatus(
      "Add a title."
    );

    return;

  }


  if (!author) {

    showPublishStatus(
      "Add an author."
    );

    return;

  }


  if (!date) {

    showPublishStatus(
      "Add a date."
    );

    return;

  }


  if (
    !/^[A-Za-z0-9_-]+\.md$/
      .test(file)
  ) {

    showPublishStatus(
      "Use a filename like article-name.md."
    );

    return;

  }


  if (!markdown) {

    showPublishStatus(
      "Write something first."
    );

    return;

  }


  const payload = {
    title,
    author,
    date,
    file,
    markdown
  };


  button.disabled =
    true;


  button.textContent =
    "Publishing…";


  showPublishStatus(
    "Publishing…",
    0
  );


  try {

    const response =
      await fetch(
        "/api/publish",
        {
          method:
            "POST",

          credentials:
            "same-origin",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify(
              payload
            )
        }
      );


    const result =
      await response.json();


    if (
      !response.ok ||
      !result.ok
    ) {

      throw new Error(
        result?.error ||
        `Publishing failed with HTTP ${response.status}.`
      );

    }


    clearDraft();


    await loadPosts();


    const published =
      posts.find(
        post =>
          post.file ===
          file
      );


    const overlay =
      $("#editor-overlay");


    overlay
      ?.classList
      .remove(
        "open"
      );


    overlay
      ?.setAttribute(
        "aria-hidden",
        "true"
      );


    await logoutWriter();


    await openReader(
      button
    );


    if (published) {

      await openPost(
        published,
        true
      );

    }

  }

  catch (error) {

    console.error(
      "Publish failed:",
      error
    );


    showPublishStatus(
      error.message ||
      "Publishing failed.",
      6000
    );

  }

  finally {

    button.disabled =
      false;


    button.textContent =
      "Publish";

  }

}


async function handleDelete(
  event
) {

  event.preventDefault();


  const button =
    event.currentTarget;


  const authenticated =
    await checkAuthentication();


  if (!authenticated) {

    openOverlay(
      "auth-overlay",
      button
    );


    return;

  }


  const file =
    $("#editor-file")
      ?.value
      .trim() ||
    "";


  if (!file) {

    showPublishStatus(
      "Enter the article filename first."
    );

    return;

  }


  if (
    !/^[A-Za-z0-9_-]+\.md$/
      .test(file)
  ) {

    showPublishStatus(
      "Invalid article filename."
    );

    return;

  }


  const existing =
    posts.find(
      post =>
        post.file ===
        file
    );


  if (!existing) {

    showPublishStatus(
      "That article is not published."
    );

    return;

  }


  const confirmed =
    window.confirm(
      `Delete "${existing.title}"?\n\nThis cannot be undone.`
    );


  if (!confirmed) {
    return;
  }


  button.disabled =
    true;


  button.textContent =
    "Deleting…";


  showPublishStatus(
    "Deleting…",
    0
  );


  try {

    const response =
      await fetch(
        `/api/posts/${encodeURIComponent(
          file
        )}`,
        {
          method:
            "DELETE",

          credentials:
            "same-origin"
        }
      );


    const result =
      await response.json();


    if (
      !response.ok ||
      !result.ok
    ) {

      throw new Error(
        result?.error ||
        `Delete failed with HTTP ${response.status}.`
      );

    }


    clearDraft();

    clearEditor();


    await loadPosts();


    const overlay =
      $("#editor-overlay");


    overlay
      ?.classList
      .remove(
        "open"
      );


    overlay
      ?.setAttribute(
        "aria-hidden",
        "true"
      );


    await logoutWriter();


    await openReader(
      button
    );

  }

  catch (error) {

    console.error(
      "Delete failed:",
      error
    );


    showPublishStatus(
      error.message ||
      "Delete failed.",
      6000
    );

  }

  finally {

    button.disabled =
      false;


    button.textContent =
      "Delete";

  }

}


function bindAuthentication() {

  $("#auth-form")
    ?.addEventListener(
      "submit",
      handleAuthentication
    );

}


function bindPublishButton() {

  $("#publish-button")
    ?.addEventListener(
      "click",
      handlePublish
    );

}


function bindDeleteButton() {

  $("#delete-button")
    ?.addEventListener(
      "click",
      handleDelete
    );

}


async function handleInitialHash() {

  const match =
    location.hash.match(
      /^#read=(.+)$/
    );


  if (!match) {
    return;
  }


  let file;


  try {

    file =
      decodeURIComponent(
        match[1]
      );

  }

  catch {

    return;

  }


  const post =
    posts.find(
      item =>
        item.file ===
        file
    );


  if (!post) {
    return;
  }


  await openReader();


  await openPost(
    post,
    false
  );

}


document.addEventListener(
  "DOMContentLoaded",
  async () => {

    bindCloseButtons();

    bindReaderButtons();

    bindWriteButtons();

    bindAuthentication();

    bindAutosave();

    bindAutomaticFilename();

    bindPublishButton();

    bindDeleteButton();


    await loadPublicConfig();

    await logoutWriter();

    await loadPosts();

    updatePreview();

    await handleInitialHash();

  }
);


window.addEventListener(
  "popstate",
  async () => {

    const match =
      location.hash.match(
        /^#read=(.+)$/
      );


    if (!match) {

      const overlay =
        $("#reader-overlay");


      if (
        overlay
          ?.classList
          .contains(
            "open"
          )
      ) {

        overlay.classList.remove(
          "open"
        );


        overlay.setAttribute(
          "aria-hidden",
          "true"
        );


        document.body.classList.remove(
          "modal-open"
        );


        document.title =
          SITE_TITLE;

      }


      return;

    }


    let file;


    try {

      file =
        decodeURIComponent(
          match[1]
        );

    }

    catch {

      return;

    }


    const post =
      posts.find(
        item =>
          item.file ===
          file
      );


    if (!post) {
      return;
    }


    openOverlay(
      "reader-overlay"
    );


    await openPost(
      post,
      false
    );

  }
);


window.addEventListener(
  "beforeunload",
  () => {

    if (editorDirty) {

      clearTimeout(
        autosaveTimer
      );


      saveDraft();

    }

  }
);