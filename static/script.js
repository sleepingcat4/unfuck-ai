const $ = selector =>
  document.querySelector(selector);

const $$ = selector =>
  [...document.querySelectorAll(selector)];


let posts = [];

let returnFocus = null;

let editorDirty = false;

let editorAuthenticated = false;

let macOSOnly = true;


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


  const flushParagraph = () => {

    if (!paragraph.length) {
      return;
    }

    html +=
      `<p>${inlineMarkdown(
        paragraph.join(" ")
      )}</p>`;

    paragraph = [];

  };


  const closeList = () => {

    if (!listType) {
      return;
    }

    html +=
      `</${listType}>`;

    listType = "";

  };


  for (
    const line of lines
  ) {

    if (
      line.startsWith("```")
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

      html +=
        "<hr>";

      continue;

    }


    if (
      line.startsWith("> ")
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
        listType !== type
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
    .forEach(
      item => {

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

      }
    );


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


  setTimeout(
    () => {

      overlay
        .querySelector(
          "button,input,textarea"
        )
        ?.focus();

    },
    30
  );

}


async function closeOverlay(
  id
) {

  const overlay =
    document.getElementById(
      id
    );


  if (!overlay) {
    return;
  }


  overlay.classList.remove(
    "open"
  );

  overlay.setAttribute(
    "aria-hidden",
    "true"
  );


  if (
    id === "editor-overlay"
  ) {

    await logoutWriter();

  }


  if (
    id === "reader-overlay"
  ) {

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


$$("[data-close]")
  .forEach(
    button => {

      button.addEventListener(
        "click",
        () => {

          closeOverlay(
            button.dataset.close
          );

        }
      );

    }
  );


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
      event.key === "Escape"
    ) {

      closeOverlay(
        open.id
      );

      return;

    }


    if (
      event.key !== "Tab"
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


    if (
      !focusable.length
    ) {
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
      ?.classList.toggle(
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
          cache:
            "no-store",

          credentials:
            "same-origin"
        }
      );


    if (
      !response.ok
    ) {

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
      "/posts/index.jsonl",
      {
        cache:
          "no-store"
      }
    );


  if (
    !response.ok
  ) {

    throw new Error(
      "Could not load writing."
    );

  }


  const text =
    await response.text();


  posts =
    text

      .split("\n")

      .map(
        line =>
          line.trim()
      )

      .filter(
        Boolean
      )

      .map(
        line => {

          try {

            return JSON.parse(
              line
            );

          }

          catch {

            return null;

          }

        }
      )

      .filter(
        Boolean
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
      `${posts.length} ` +
      `${posts.length === 1
        ? "post"
        : "posts"
      }`;

  }


  if (!list) {
    return;
  }


  if (
    !posts.length
  ) {

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
              ? `<span>·</span>
                 <span>${escapeHTML(
                   readableDate
                 )}</span>`
              : ""
          }
        </small>
      `;


      button.addEventListener(
        "click",
        () =>
          openPost(
            post,
            true
          )
      );


      list.append(
        button
      );

    }
  );

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
    .forEach(
      item => {

        item.classList.toggle(
          "active",
          item.dataset.file ===
            post.file
        );

      }
    );


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


    if (
      !response.ok
    ) {

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
              post.date || ""
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
        "Untitled"
      } — ${SITE_TITLE}`;


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
      ?.scrollTo(
        {
          top: 0,
          behavior:
            "smooth"
        }
      );

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


  if (
    !posts.length
  ) {

    await loadPosts();

  }


  if (
    posts.length &&
    !$(".post-item.active")
  ) {

    await openPost(
      posts[0],
      false
    );

  }

}


[
  "#open-reader",
  "#hero-read",
  "#latest-read",
  "#footer-read"
]
.forEach(
  selector => {

    const button =
      $(selector);


    if (!button) {
      return;
    }


    button.addEventListener(
      "click",
      event => {

        openReader(
          event.currentTarget
        );

      }
    );

  }
);


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


    if (
      !response.ok
    ) {

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


    const phraseInput =
      $("#auth-phrase");

    const status =
      $("#auth-status");


    if (phraseInput) {

      phraseInput.value =
        "";

    }


    if (status) {

      status.textContent =
        "";

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


$("#open-write")
  ?.addEventListener(
    "click",
    event => {

      startWriting(
        event.currentTarget
      );

    }
  );


$("#auth-form")
  ?.addEventListener(
    "submit",
    async event => {

      event.preventDefault();


      const input =
        $("#auth-phrase");

      const status =
        $("#auth-status");

      const button =
        event
          .currentTarget
          .querySelector(
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
                JSON.stringify(
                  {
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
                  }
                )
            }
          );


        let result;


        try {

          result =
            await response.json();

        }

        catch {

          throw new Error(
            "Server returned an invalid response."
          );

        }


        if (
          !response.ok ||
          !result.ok
        ) {

          throw new Error(
            result.error ||
            "Access denied."
          );

        }


        const authenticated =
          await checkAuthentication();


        if (
          !authenticated
        ) {

          throw new Error(
            "Authentication session was not created."
          );

        }


        editorAuthenticated =
          true;


        if (input) {

          input.value =
            "";

        }


        if (status) {

          status.textContent =
            "";

        }


        await openEditor();

      }

      catch (error) {

        editorAuthenticated =
          false;


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
  );


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
          $(selector)?.value ||
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

  catch {
  }


  editorDirty =
    Object.values(
      draft
    )
    .some(
      Boolean
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


      if (
        element &&
        !element.value
      ) {

        element.value =
          draft[selector] ||
          "";

      }

    }
  );


  editorDirty =
    Object.values(
      draft
    )
    .some(
      Boolean
    );

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

      : '<p style="opacity:.4">' +
        "Preview will appear here." +
        "</p>";

}


editorFields.forEach(
  selector => {

    $(selector)
      ?.addEventListener(
        "input",
        () => {

          saveDraft();

          updatePreview();

        }
      );

  }
);


async function openEditor() {

  const authenticated =
    await checkAuthentication();


  if (
    !authenticated ||
    !editorAuthenticated
  ) {

    editorAuthenticated =
      false;


    const input =
      $("#auth-phrase");

    const status =
      $("#auth-status");


    if (input) {

      input.value =
        "";

    }


    if (status) {

      status.textContent =
        "Enter the publishing phrase.";

    }


    openOverlay(
      "auth-overlay",
      $("#open-write")
    );


    return;

  }


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
        now.getTimezoneOffset() *
        60000
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


$("#editor-title")
  ?.addEventListener(
    "input",
    event => {

      const file =
        $("#editor-file");


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

    }
  );


$("#editor-file")
  ?.addEventListener(
    "input",
    event => {

      event.target.dataset.manual =
        "true";

    }
  );


function showPublishStatus(
  message
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


  showPublishStatus.timer =
    setTimeout(
      () => {

        element.classList.remove(
          "visible"
        );

      },
      3000
    );

}


$("#publish-button")
  ?.addEventListener(
    "click",
    async event => {

      const authenticated =
        await checkAuthentication();


      if (
        !authenticated ||
        !editorAuthenticated
      ) {

        editorAuthenticated =
          false;


        const editorOverlay =
          $("#editor-overlay");


        if (editorOverlay) {

          editorOverlay.classList.remove(
            "open"
          );

          editorOverlay.setAttribute(
            "aria-hidden",
            "true"
          );

        }


        const status =
          $("#auth-status");


        if (status) {

          status.textContent =
            "Authentication required.";

        }


        openOverlay(
          "auth-overlay",
          event.currentTarget
        );


        return;

      }


      const payload = {

        title:
          $("#editor-title")
            ?.value
            .trim() ||
          "",

        author:
          $("#editor-author")
            ?.value
            .trim() ||
          "",

        date:
          $("#editor-date")
            ?.value
            .trim() ||
          "",

        file:
          $("#editor-file")
            ?.value
            .trim() ||
          "",

        markdown:
          markdownEditor
            ?.value
            .trim() ||
          ""
      };


      if (
        !payload.title
      ) {

        showPublishStatus(
          "Add a title."
        );

        return;

      }


      if (
        !payload.author
      ) {

        showPublishStatus(
          "Add an author."
        );

        return;

      }


      if (
        !payload.date
      ) {

        showPublishStatus(
          "Add a date."
        );

        return;

      }


      if (
        !/^[A-Za-z0-9_-]+\.md$/
          .test(
            payload.file
          )
      ) {

        showPublishStatus(
          "Use a filename like article-name.md."
        );

        return;

      }


      if (
        !payload.markdown
      ) {

        showPublishStatus(
          "Write something first."
        );

        return;

      }


      const button =
        event.currentTarget;


      button.disabled =
        true;

      button.textContent =
        "Publishing…";


      showPublishStatus(
        "Publishing…"
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


        let result;


        try {

          result =
            await response.json();

        }

        catch {

          throw new Error(
            "Server returned an invalid response."
          );

        }


        if (
          response.status ===
          401
        ) {

          editorAuthenticated =
            false;


          const editorOverlay =
            $("#editor-overlay");


          if (editorOverlay) {

            editorOverlay.classList.remove(
              "open"
            );

            editorOverlay.setAttribute(
              "aria-hidden",
              "true"
            );

          }


          const status =
            $("#auth-status");


          if (status) {

            status.textContent =
              "Session expired. Enter the publishing phrase again.";

          }


          openOverlay(
            "auth-overlay",
            button
          );


          throw new Error(
            "Session expired."
          );

        }


        if (
          !response.ok ||
          !result.ok
        ) {

          throw new Error(
            result.error ||
            "Publishing failed."
          );

        }


        const saveState =
          $("#save-state");


        if (saveState) {

          saveState.textContent =
            "Published";

        }


        editorDirty =
          false;


        try {

          localStorage.removeItem(
            DRAFT_KEY
          );

        }

        catch {
        }


        await logoutWriter();


        await loadPosts();


        const published =
          posts.find(
            post =>
              post.file ===
              payload.file
          );


        const editorOverlay =
          $("#editor-overlay");


        if (editorOverlay) {

          editorOverlay.classList.remove(
            "open"
          );

          editorOverlay.setAttribute(
            "aria-hidden",
            "true"
          );

        }


        document.body.classList.remove(
          "modal-open"
        );


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

        showPublishStatus(
          error.message ||
          "Publishing failed."
        );

      }

      finally {

        button.disabled =
          false;

        button.textContent =
          "Publish";

      }

    }
  );


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


document.addEventListener(
  "DOMContentLoaded",
  async () => {

    await loadPublicConfig();

    await logoutWriter();

    await loadPosts();


    const match =
      location.hash.match(
        /^#read=(.+)$/
      );


    if (match) {

      const file =
        decodeURIComponent(
          match[1]
        );


      const post =
        posts.find(
          item =>
            item.file ===
            file
        );


      if (post) {

        await openReader();

        await openPost(
          post,
          false
        );

      }

    }

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

      if (
        $("#reader-overlay")
          ?.classList
          .contains(
            "open"
          )
      ) {

        await closeOverlay(
          "reader-overlay"
        );

      }


      return;

    }


    const file =
      decodeURIComponent(
        match[1]
      );


    const post =
      posts.find(
        item =>
          item.file ===
          file
      );


    if (post) {

      openOverlay(
        "reader-overlay"
      );


      await openPost(
        post,
        false
      );

    }

  }
);