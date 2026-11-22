/* EpubMe browser button: turns the article page you are reading into an EPUB and
   downloads it. Runs entirely in the browser, so it works on pages behind a library
   login (e.g. Cambridge Core through Bar-Ilan). No OCR, no server: the text comes
   from the page itself.

   Understands the Cambridge Core article layout (same rules as
   scripts/html_article.py: citation_* meta tags, div.abstract, div.sec sections,
   div.fig-ada figures, numbered notes in #footnotes-list). Other pages fall back to
   <article>/<main> with headings, paragraphs, lists, quotes, tables and figures.

   Output follows the repo's EPUB conventions: EPUB 3 with nav, metadata title and
   author only, numbered notes as popup footnotes, Hebrew pages RTL (dir="rtl" on
   lists, tables, boxes, figures; page-progression rtl) with David Libre embedded
   when the font can be downloaded.

   Edit this file, then run `python3 scripts/build_bookmarklet.py` to regenerate
   browser/bookmarklet.txt. Rules for this file: no multi-line template literals
   (the build trims indentation) and no block comments inside code lines. */
(async function () {
  'use strict';
  var XHTML = 'http://www.w3.org/1999/xhtml';
  var OPS = 'http://www.idpf.org/2007/ops';
  var XMLNS = 'http://www.w3.org/2000/xmlns/';
  var FONT_BASE = 'https://raw.githubusercontent.com/google/fonts/main/ofl/davidlibre/';
  var doc = document;
  var here = location.href;

  // ---------- status box ----------
  var box = doc.createElement('div');
  box.setAttribute('style', 'position:fixed;z-index:2147483647;top:12px;right:12px;max-width:360px;' +
    'background:#222;color:#fff;font:14px/1.4 sans-serif;padding:10px 14px;border-radius:8px;' +
    'box-shadow:0 2px 10px rgba(0,0,0,.4);white-space:pre-wrap;direction:ltr;text-align:left');
  box.id = 'epubme-status';
  (doc.body || doc.documentElement).appendChild(box);
  function status(msg, done) {
    box.textContent = 'EpubMe: ' + msg;
    if (done) setTimeout(function () { box.remove(); }, 12000);
  }
  status('building...');


  async function run() {
    var art = extract();
    status('building "' + art.title + '"...');
    var book = render(art);
    await fetchImages(book);
    var fonts = art.rtl ? await fetchFonts() : [];
    var files = pack(art, book, fonts);
    var blob = await zip(files);
    var name = libraryName(art) + '.epub';
    var file = blob;
    try { file = new File([blob], name, { type: 'application/epub+zip' }); } catch (e) { }
    var url = URL.createObjectURL(file);
    // iPhone/iPad Safari saves blob downloads under a random id ("4363948c-...")
    // and ignores the name, so there the box offers the share sheet instead,
    // which keeps the name (Save to Files, or send to an app).
    var ios = /iP(hone|ad|od)/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
    var canShare = ios && file !== blob && navigator.canShare && navigator.canShare({ files: [file] });
    if (!canShare) {
      var a = doc.createElement('a');
      a.href = url;
      a.download = name;
      (doc.body || doc.documentElement).appendChild(a);
      a.click();
      setTimeout(function () { a.remove(); }, 1000);
    }
    setTimeout(function () { URL.revokeObjectURL(url); }, 600000);
    var lost = book.images.filter(function (im) { return !im.data; }).length;
    window.__epubMeSummary = { name: name, notes: book.noteCount, figures: book.images.length - lost,
      lostFigures: lost, sections: book.headings.length, rtl: art.rtl, fonts: fonts.length };
    var counts = book.headings.length + ' sections, ' + book.noteCount + ' notes, ' +
      (book.images.length - lost) + ' figures' + (lost ? ' (' + lost + ' figures could not be downloaded)' : '');
    if (!canShare) { status('saved ' + name + '\n' + counts, true); return; }
    status('ready: ' + name + '\n' + counts + '\n');
    var btn = doc.createElement('button');
    btn.textContent = 'Save / share EPUB';
    btn.setAttribute('style', 'display:block;margin-top:8px;padding:8px 12px;font:15px sans-serif;border-radius:6px;border:0;background:#fff;color:#000');
    // files only: on iOS, adding a title or text to the share drops apps such as
    // Dropbox that accept a file but not text from the menu
    btn.onclick = function () {
      navigator.share({ files: [file] }).then(function () { box.remove(); }, function () { });
    };
    var close = doc.createElement('button');
    close.textContent = 'Close';
    close.setAttribute('style', 'margin-top:6px;padding:4px 10px;font:13px sans-serif;border-radius:6px;border:1px solid #888;background:none;color:#fff');
    close.onclick = function () { box.remove(); };
    box.appendChild(btn);
    box.appendChild(close);
  }

  // ---------- reading the page ----------
  function meta(name) {
    return Array.prototype.map.call(doc.querySelectorAll('meta[name="' + name + '"],meta[property="' + name + '"]'),
      function (m) { return (m.getAttribute('content') || '').trim(); }).filter(Boolean);
  }
  function txt(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function uniq(a) { return a.filter(function (x, i) { return a.indexOf(x) === i; }); }

  function isRtl(root) {
    var html = doc.documentElement;
    var lang = (html.getAttribute('lang') || '').toLowerCase();
    if (/^(he|iw|yi|ar|fa)\b/.test(lang)) return true;
    var t = (root.textContent || '').slice(0, 30000);
    var heb = (t.match(/[֐-׿؀-ۿ]/g) || []).length;
    var lat = (t.match(/[A-Za-z]/g) || []).length;
    return heb > lat;
  }

  function extract() {
    var title = meta('citation_title')[0] || meta('og:title')[0] || meta('dc.title')[0];
    var h1 = doc.querySelector('article h1, main h1, h1');
    if (!title) title = h1 ? txt(h1.textContent) : txt(doc.title) || 'Article';
    title = dropSiteName(txt(title));
    var authors = uniq(meta('citation_author'));
    if (!authors.length) authors = uniq(meta('dc.creator').concat(meta('author')));
    // WordPress puts the login of whoever posted it ("wsr_kulna"), not the writer
    authors = authors.filter(function (a) { return !(/^[\w.\-]+$/.test(a) && (/[_\d]/.test(a) || a === a.toLowerCase())); });

    var roots = [];
    var notesBox = doc.querySelector('#footnotes-list');
    var abstract = doc.querySelector('div.abstract');
    var kw = doc.querySelector('div.keywords');
    var secs = Array.prototype.filter.call(doc.querySelectorAll('div.sec'), function (d) {
      return /^sec\d+$/.test(d.id) && d.id !== 'sec0';
    });
    secs = secs.filter(function (d) { return !secs.some(function (o) { return o !== d && o.contains(d); }); });
    var cambridge = secs.length > 0;
    if (cambridge) {
      if (abstract) roots.push({ kind: 'abstract', el: abstract, keywords: kw });
      secs.forEach(function (s) { roots.push({ kind: 'sec', el: s }); });
      var ack = doc.querySelector('div.ack');
      if (ack) roots.push({ kind: 'sec', el: ack });
      var refs = doc.querySelector('#references-list, div.ref-list, div.references');
      if (refs && !(notesBox && notesBox.contains(refs))) roots.push({ kind: 'refs', el: refs });
    } else {
      var main = mainRoot();
      roots.push({ kind: 'sec', el: main });
      // a short all-bold first paragraph is the writer's name ("אריאל חנוך")
      var first = main.querySelector('p');
      var b = first && first.querySelector('strong, b');
      if (!authors.length && b && txt(b.textContent) === txt(first.textContent) &&
          /^[^.,:;!?()]{2,40}$/.test(txt(b.textContent)) && txt(b.textContent).split(' ').length <= 4) {
        authors = [txt(b.textContent)];
        SKIP_ELS.push(first);
      }
    }
    var rtl = isRtl(roots[0].el);
    var lang = (doc.documentElement.getAttribute('lang') || '').split('-')[0].toLowerCase();
    if (rtl && !/^(he|iw|yi|ar|fa)$/.test(lang)) lang = 'he';
    if (lang === 'iw') lang = 'he';
    if (!/^[a-z]{2,3}$/.test(lang)) lang = rtl ? 'he' : 'en';
    var plainHeads = !cambridge && !roots[0].el.querySelector('h2, h3, h4');
    return { title: title, authors: authors, roots: roots, rtl: rtl, lang: lang,
      cambridge: cambridge, notesBox: notesBox, plainHeads: plainHeads, year: pubYear() };
  }

  function dropSiteName(t) {
    var site = txt(meta('og:site_name')[0] || meta('application-name')[0] || '');
    if (!site) return t;
    var i = t.lastIndexOf(site);
    if (i > 0 && i + site.length === t.length) {
      var rest = t.slice(0, i).replace(/[\s\-|\u2013\u2014:\u00b7]+$/, '');
      if (rest && rest.length < i) return rest;
    }
    return t;
  }

  function mainRoot() {
    // the post body itself, when the site marks it (WordPress, Elementor, schema.org)
    var BODY = '.entry-content, .elementor-widget-theme-post-content, [itemprop="articleBody"], .post-content, .article-body, .article-content, .post-body';
    var bodies = Array.prototype.filter.call(doc.querySelectorAll(BODY), function (c) {
      return Array.prototype.reduce.call(c.querySelectorAll('p'), function (s, p) { return s + p.textContent.length; }, 0) > 500;
    });
    if (bodies.length) return bodies.filter(function (c) { return !bodies.some(function (o) { return o !== c && o.contains(c); }); })[0];
    var cands = Array.prototype.slice.call(doc.querySelectorAll('article, main, [role="main"], #content, .content'));
    var best = null, bestLen = 0;
    cands.forEach(function (c) {
      var n = Array.prototype.reduce.call(c.querySelectorAll('p'), function (s, p) { return s + p.textContent.length; }, 0);
      if (n > bestLen * 1.3 || (best && best.contains(c) && n > bestLen * 0.8)) { best = c; bestLen = n; }
    });
    return best || doc.body;
  }

  // ---------- building XHTML ----------
  var SKIP = /^(script|style|noscript|template|button|input|select|textarea|form|nav|iframe|object|embed|video|audio|canvas|svg|math|dialog|link|meta|label)$/;
  var SKIP_CLASS = /(^|\s)(show-for-sr|sr-only|visually-hidden|screen-reader-text|hide|hidden|share|social|related|advert|ad-|cookie|newsletter|toolbar|breadcrumb)(\s|$)/i;
  var SKIP_ELS = [];   // elements used elsewhere (the byline paragraph)
  var NOTE_BOX = '#footnotes-list, .footnotes, [role="doc-endnotes"], [role="doc-footnotes"], ol.references, section.footnotes, div.footnotes, #footnotes, .endnotes';

  function render(art) {
    var out = doc.implementation.createDocument(XHTML, 'html', null);
    var html = out.documentElement;
    html.setAttributeNS(XMLNS, 'xmlns:epub', OPS);
    var book = { out: out, images: [], headings: [], notes: [], noteById: {}, noteCount: 0, rtl: art.rtl, art: art };
    var body = el(book, 'body');
    var ids = {};
    function uid(base) {
      var id = base, n = 1;
      while (ids[id]) id = base + '-' + (++n);
      ids[id] = 1;
      return id;
    }
    book.uid = uid;

    var h = el(book, 'h1'); h.setAttribute('id', uid('title')); h.textContent = art.title; body.appendChild(h);
    if (art.authors.length) {
      var by = el(book, 'p'); by.setAttribute('class', 'byline'); by.textContent = art.authors.join(', '); body.appendChild(by);
    }

    art.roots.forEach(function (r) {
      if (r.kind === 'abstract') {
        if (!r.el.querySelector('h2,h3')) heading(book, body, 2, art.rtl ? 'תקציר' : 'Abstract');
        walk(book, r.el, body);
        if (r.keywords) keywords(book, r.keywords, body);
      } else if (r.kind === 'refs') {
        var sec = el(book, 'section'); sec.setAttribute('class', 'references');
        if (!r.el.querySelector('h2,h3')) heading(book, sec, 2, art.rtl ? 'מקורות' : 'References');
        walk(book, r.el, sec);
        body.appendChild(sec);
      } else {
        walk(book, r.el, body);
      }
    });

    if (book.notes.length) {
      var ns = el(book, 'section');
      ns.setAttributeNS(OPS, 'epub:type', 'footnotes');
      ns.setAttribute('class', 'footnotes');
      var nh = heading(book, ns, 2, art.rtl ? 'הערות' : 'Notes');
      nh.setAttribute('class', 'notes-title');
      // notes may reference further notes: book.notes grows while we fill them
      for (var i = 0; i < book.notes.length; i++) ns.appendChild(noteAside(book, book.notes[i]));
      body.appendChild(ns);
    }

    var head = el(book, 'head');
    var t = el(book, 'title'); t.textContent = art.title; head.appendChild(t);
    var link = el(book, 'link'); link.setAttribute('rel', 'stylesheet'); link.setAttribute('type', 'text/css'); link.setAttribute('href', 'style.css');
    head.appendChild(link);
    html.appendChild(head);
    html.appendChild(body);
    html.setAttribute('lang', art.lang);
    html.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:lang', art.lang);
    if (art.rtl) {
      html.setAttribute('dir', 'rtl');
      Array.prototype.forEach.call(body.querySelectorAll('ol,ul,li,table,section,aside,figure,blockquote'), function (e) {
        if (!e.hasAttribute('dir')) e.setAttribute('dir', 'rtl');
      });
    }
    return book;
  }

  function el(book, name) { return book.out.createElementNS(XHTML, name); }

  function heading(book, parent, level, text, src) {
    var h = el(book, 'h' + level);
    if (src) inline(book, src, h); else h.textContent = text;
    trimEdges(h);
    if (!txt(h.textContent)) return h;
    h.setAttribute('id', book.uid('s' + (book.headings.length + 1)));
    book.headings.push({ level: level, id: h.getAttribute('id'), text: txt(h.textContent) });
    parent.appendChild(h);
    return h;
  }

  function skipped(n) {
    if (n.nodeType !== 1) return false;
    var name = n.localName.toLowerCase();
    if (SKIP.test(name) || SKIP_ELS.indexOf(n) >= 0) return true;
    if (n.hidden || n.getAttribute('aria-hidden') === 'true') return true;
    var cls = n.getAttribute('class') || '';
    if (SKIP_CLASS.test(cls)) return true;
    if (/display\s*:\s*none/i.test(n.getAttribute('style') || '')) return true;
    return false;
  }

  function isNoteRef(a) {
    if (a.localName !== 'a') return false;
    var href = a.getAttribute('href') || '';
    if (href.charAt(0) !== '#' || href.length < 2) return false;
    // a note mark is short ("12", "[3]", "*"); "Ibid." linking to an earlier note stays text
    var shown = Array.prototype.filter.call(a.childNodes, function (n) { return !skipped(n); })
      .map(function (n) { return n.textContent; }).join('');
    if (!/^\s*[\[(]?[\d*\u2020\u2021]{1,4}[\])]?\s*$/.test(shown)) return false;
    var cls = a.getAttribute('class') || '';
    if (/(^|\s)(fn|footnote-ref|noteref)(\s|$)/.test(cls) || a.getAttribute('role') === 'doc-noteref') return true;
    if (/noteref/.test(a.getAttribute('epub:type') || '')) return true;
    var target = byId(href.slice(1));
    return !!(target && target.closest && target.closest(NOTE_BOX));
  }

  function byId(id) {
    try { return doc.getElementById(decodeURIComponent(id)); } catch (e) { return doc.getElementById(id); }
  }

  function noteRef(book, a, parent) {
    var id = (a.getAttribute('href') || '').slice(1);
    var src = byId(id);
    if (!src) { parent.appendChild(book.out.createTextNode(txt(a.textContent))); return; }
    var item = src.closest('li, aside, [id^="fn"], div.circle-list__item') || src;
    var key = item.id || id;
    var note = book.noteById[key];
    if (!note) {
      var num = noteNumber(item, a, book);
      note = { id: book.uid('fn' + num), num: num, src: item, refs: [] };
      book.noteById[key] = note;
      book.notes.push(note);
      book.noteCount++;
    }
    var ref = el(book, 'a');
    var rid = book.uid('fnref' + note.num);
    note.refs.push(rid);
    ref.setAttribute('id', rid);
    ref.setAttribute('href', '#' + note.id);
    ref.setAttribute('class', 'noteref');
    ref.setAttributeNS(OPS, 'epub:type', 'noteref');
    ref.setAttribute('role', 'doc-noteref');
    var sup = el(book, 'sup'); sup.textContent = note.num;
    ref.appendChild(sup);
    parent.appendChild(ref);
  }

  function noteNumber(item, a, book) {
    var lab = item.querySelector('.label');
    var m = /\d+/.exec(lab ? lab.textContent : a.textContent);
    if (m && !book.notes.some(function (n) { return n.num === m[0]; })) return m[0];
    return String(book.notes.length + 1);
  }

  function noteAside(book, note) {
    var aside = el(book, 'aside');
    aside.setAttribute('id', note.id);
    aside.setAttributeNS(OPS, 'epub:type', 'footnote');
    aside.setAttribute('role', 'doc-footnote');
    var tmp = el(book, 'div');
    var src = note.src.cloneNode(true);
    Array.prototype.forEach.call(src.querySelectorAll('.label, .circle-list__item__indicator, a[href^="#fnref"], a.footnote-back, a.footnote-backref, [role="doc-backlink"], a[href^="#"]'),
      function (x) {
        if (x.localName !== 'a' || x.getAttribute('href').indexOf('#fnref') === 0 || /^[\s\u21a9\u2191\u2934\ufe0e^]*$/.test(x.textContent)) x.remove();
      });
    walk(book, src, tmp);
    var first = tmp.firstChild;
    if (!first || first.localName !== 'p') { first = el(book, 'p'); tmp.insertBefore(first, tmp.firstChild); }
    var back = el(book, 'a');
    back.setAttribute('href', '#' + note.refs[0]);
    back.setAttribute('class', 'noteback');
    back.textContent = note.num + '.';
    first.insertBefore(book.out.createTextNode(' '), first.firstChild);
    first.insertBefore(back, first.firstChild);
    while (tmp.firstChild) aside.appendChild(tmp.firstChild);
    return aside;
  }

  function keywords(book, kw, parent) {
    var leaves = Array.prototype.filter.call(kw.querySelectorAll('a, li, span'), function (x) {
      return !x.querySelector('a, li, span') && txt(x.textContent) && txt(x.textContent) !== 'Keywords';
    }).map(function (x) { return txt(x.textContent); });
    leaves = uniq(leaves);
    if (!leaves.length) leaves = [txt(kw.textContent).replace(/^Keywords\s*/, '')];
    var p = el(book, 'p'); p.setAttribute('class', 'keywords');
    var b = el(book, 'strong'); b.textContent = (book.rtl ? 'מילות מפתח:' : 'Keywords:');
    p.appendChild(b);
    p.appendChild(book.out.createTextNode(' ' + leaves.join(', ')));
    parent.appendChild(p);
  }

  var BLOCK = /^(p|div|section|article|main|header|footer|aside|blockquote|figure|figcaption|table|ol|ul|li|dl|dt|dd|h[1-6]|hr|pre)$/;

  function hasBlockChild(n) {
    for (var c = n.firstElementChild; c; c = c.nextElementSibling) {
      if (BLOCK.test(c.localName) && !skipped(c)) return true;
    }
    return false;
  }

  // block-level walk: copies headings, paragraphs, lists, quotes, figures, tables
  function walk(book, src, parent) {
    var loose = null;   // collects inline content that sits directly in a container
    function flush() {
      if (loose) { trimEdges(loose); if (txt(loose.textContent) || loose.querySelector('img')) parent.appendChild(loose); loose = null; }
    }
    for (var c = src.firstChild; c; c = c.nextSibling) {
      if (c.nodeType === 3) {
        if (/\S/.test(c.nodeValue)) { loose = loose || el(book, 'p'); inlineNode(book, c, loose); }
        continue;
      }
      if (c.nodeType !== 1 || skipped(c)) continue;
      var name = c.localName.toLowerCase();
      var cls = c.getAttribute('class') || '';
      if (c !== src && c.matches && c.matches(NOTE_BOX)) {
        continue;   // notes are collected from their references
      }
      if (!BLOCK.test(name) && !/fig-ada|table-wrap|disp-quote|boxed-text/.test(cls)) {
        loose = loose || el(book, 'p'); inlineNode(book, c, loose); continue;
      }
      flush();
      if (/^h[1-6]$/.test(name)) {
        var lvl = +name[1];
        if (lvl === 1 && txt(c.textContent) === book.art.title) continue;
        heading(book, parent, Math.min(Math.max(lvl, 2), 4), null, c);
      } else if (name === 'p' || name === 'pre' || name === 'dt' || name === 'dd') {
        if (hasBlockChild(c)) { walk(book, c, parent); continue; }
        var p = el(book, 'p');
        inline(book, c, p);
        trimEdges(p);
        if (plainHeading(book, p, parent, c)) continue;
        book.lastHead = 0;
        if (txt(p.textContent) || p.querySelector('img')) parent.appendChild(p);
      } else if (name === 'ol' || name === 'ul') {
        list(book, c, parent);
      } else if (/fig-ada/.test(cls) || name === 'figure') {
        figure(book, c, parent);
      } else if (/table-wrap/.test(cls) || name === 'table') {
        table(book, c, parent);
      } else if (name === 'blockquote' || /disp-quote/.test(cls)) {
        var q = el(book, 'blockquote');
        walk(book, c, q);
        if (q.firstChild) parent.appendChild(q);
      } else if (/boxed-text/.test(cls)) {
        var bx = el(book, 'div'); bx.setAttribute('class', 'box');
        walk(book, c, bx);
        if (bx.firstChild) parent.appendChild(bx);
      } else if (name === 'hr' || name === 'figcaption') {
        continue;
      } else {
        walk(book, c, parent);   // div, section, article, li outside a list...
      }
    }
    flush();
  }

  // Pages without h2/h3 often set section titles as short plain paragraphs
  // ("פתיחה", "חלק א'"). A run of them is title + subtitle (h2, h3); once such a
  // pair has been seen, a lone short paragraph is a subsection title (h3).
  function plainHeading(book, p, parent, src) {
    if (!book.art.plainHeads || parent.localName !== 'body') return false;
    var t = txt(p.textContent);
    if (!t || t.length > 60 || t.split(' ').length > 8) return false;
    // ends like a sentence or a quote; a Hebrew numeral ("חלק א'") is fine
    if (/[.,;:\u05f4"\u201d)\]]$/.test(t) || (/'$/.test(t) && !/(^|\s)[\u05d0-\u05ea]{1,2}'$/.test(t))) return false;
    if (p.querySelector('img, a, br')) return false;
    var next = src.nextElementSibling;
    if (!next || next.localName !== 'p' || txt(next.textContent).length < 80) {
      if (!next || next.localName !== 'p' || txt(next.textContent).length > 60) return false;
    }
    var level = book.lastHead === 2 ? 3 : (book.sawPair && txt(next.textContent).length >= 80 ? 3 : 2);
    if (book.lastHead === 2) book.sawPair = true;
    heading(book, parent, level, t);
    book.lastHead = level;
    return true;
  }

  function list(book, src, parent) {
    var items = Array.prototype.filter.call(src.children, function (li) { return li.localName === 'li'; });
    // items that carry their own label ("(i)", "a.") must not get a second number
    var labelled = items.length && items.every(function (li) { return li.querySelector('.label'); });
    var out = el(book, labelled || src.localName !== 'ol' ? 'ul' : 'ol');
    if (labelled) out.setAttribute('class', 'labelled');
    var start = src.getAttribute('start');
    if (start && /^\d+$/.test(start)) out.setAttribute('start', start);
    for (var li = src.firstElementChild; li; li = li.nextElementSibling) {
      if (li.localName !== 'li' || skipped(li)) continue;
      var o = el(book, 'li');
      inline(book, li, o);
      trimEdges(o);
      if (txt(o.textContent) || o.querySelector('img,ol,ul')) out.appendChild(o);
    }
    if (out.firstChild) parent.appendChild(out);
  }

  function figure(book, src, parent) {
    var img = src.querySelector('img');
    var cap = src.querySelector('.caption, figcaption');
    var fig = el(book, 'figure');
    var o = null;
    if (img) {
      var urls = imageUrls(img);
      if (urls.length) {
        o = el(book, 'img');
        var n = book.images.length + 1;
        o.setAttribute('alt', 'Figure ' + n);
        fig.appendChild(o);
        book.images.push({ node: o, urls: urls, live: img, fig: fig, n: n });
      }
    }
    if (cap) {
      var fc = el(book, 'figcaption');
      inline(book, cap, fc);
      trimEdges(fc);
      if (txt(fc.textContent)) {
        fig.appendChild(fc);
        if (o) o.setAttribute('alt', txt(fc.textContent).slice(0, 300));
      }
    }
    if (fig.firstChild) parent.appendChild(fig);
  }

  function imageUrls(img) {
    var raw = [img.getAttribute('data-original-image'), img.getAttribute('data-src'), img.currentSrc,
      img.getAttribute('src'), img.getAttribute('data-lazy-src')];
    var ss = img.getAttribute('srcset') || img.getAttribute('data-srcset');
    if (ss) raw.push(ss.split(',').pop().trim().split(/\s+/)[0]);
    var urls = [];
    raw.forEach(function (u) {
      if (!u) return;
      if (/^data:/.test(u)) { if (u.length > 400) urls.push(u); return; }
      try { urls.push(new URL(u, here).href); } catch (e) { }
    });
    urls = uniq(urls);
    // same-origin first: through a library proxy those are the ones that work
    var origin = location.origin;
    return urls.filter(function (u) { return u.indexOf(origin) === 0; })
      .concat(urls.filter(function (u) { return u.indexOf(origin) !== 0; }));
  }

  function table(book, src, parent) {
    var t = src.localName === 'table' ? src : src.querySelector('table');
    var cap = src.querySelector('.caption, caption');
    if (!t) { walk(book, src, parent); return; }
    var out = el(book, 'table');
    if (cap) {
      var c = el(book, 'caption'); inline(book, cap, c); trimEdges(c);
      if (txt(c.textContent)) out.appendChild(c);
    }
    Array.prototype.forEach.call(t.rows, function (r) {
      var sectionName = r.parentNode.localName === 'thead' ? 'thead' : (r.parentNode.localName === 'tfoot' ? 'tfoot' : 'tbody');
      var sec = out.lastElementChild;
      if (!sec || sec.localName !== sectionName) { sec = el(book, sectionName); out.appendChild(sec); }
      var tr = el(book, 'tr');
      Array.prototype.forEach.call(r.cells, function (cell) {
        var o = el(book, cell.localName === 'th' ? 'th' : 'td');
        ['colspan', 'rowspan'].forEach(function (k) {
          var v = cell.getAttribute(k); if (v && /^\d+$/.test(v) && v !== '1') o.setAttribute(k, v);
        });
        inline(book, cell, o);
        trimEdges(o);
        tr.appendChild(o);
      });
      sec.appendChild(tr);
    });
    if (out.querySelector('tr')) parent.appendChild(out);
    var foot = src.querySelector('.table-wrap-foot, .table-foot');
    if (foot) walk(book, foot, parent);
  }

  // inline content: emphasis, sup/sub, line breaks, note references; other tags unwrapped
  function inline(book, src, parent) {
    for (var c = src.firstChild; c; c = c.nextSibling) inlineNode(book, c, parent);
  }

  function inlineNode(book, c, parent) {
    if (c.nodeType === 3) { appendText(book, parent, c.nodeValue); return; }
    if (c.nodeType !== 1 || skipped(c)) return;
    var name = c.localName.toLowerCase();
    if (name === 'a' && isNoteRef(c)) { noteRef(book, c, parent); return; }
    if (name === 'sup' && c.querySelector('a') && isNoteRef(c.querySelector('a')) && txt(c.textContent) === txt(c.querySelector('a').textContent)) {
      noteRef(book, c.querySelector('a'), parent); return;
    }
    var map = { em: 'em', i: 'em', cite: 'em', strong: 'strong', b: 'strong', sup: 'sup', sub: 'sub', code: 'code', small: 'small', u: 'span' };
    if (name === 'br') { parent.appendChild(el(book, 'br')); return; }
    if (name === 'img') {
      var urls = imageUrls(c);
      if (!urls.length || (c.width && c.width < 4)) return;
      var o = el(book, 'img'); o.setAttribute('alt', c.getAttribute('alt') || '');
      book.images.push({ node: o, urls: urls, live: c, n: book.images.length + 1 });
      parent.appendChild(o); return;
    }
    if ((name === 'ol' || name === 'ul') && parent.localName === 'li') { list(book, c, parent); return; }
    if (map[name]) {
      var e = el(book, map[name]);
      inline(book, c, e);
      if (txt(e.textContent) || e.querySelector('img,a')) parent.appendChild(e);
      return;
    }
    if (BLOCK.test(name)) appendText(book, parent, ' ');
    inline(book, c, parent);
    if (BLOCK.test(name)) appendText(book, parent, ' ');
  }

  function appendText(book, parent, s) {
    s = s.replace(/[\s ]+/g, function (w) { return / /.test(w) && !/[\t\n ]/.test(w) ? ' ' : ' '; });
    var last = parent.lastChild;
    if (last && last.nodeType === 3) {
      if (/ $/.test(last.nodeValue) && /^ /.test(s)) s = s.slice(1);
      last.nodeValue += s;
    } else {
      parent.appendChild(book.out.createTextNode(s));
    }
  }

  function trimEdges(e) {
    var f = e.firstChild;
    while (f && f.nodeType === 3 && !/\S/.test(f.nodeValue)) { e.removeChild(f); f = e.firstChild; }
    if (f && f.nodeType === 3) f.nodeValue = f.nodeValue.replace(/^\s+/, '');
    var l = e.lastChild;
    while (l && l.nodeType === 3 && !/\S/.test(l.nodeValue)) { e.removeChild(l); l = e.lastChild; }
    if (l && l.nodeType === 3) l.nodeValue = l.nodeValue.replace(/\s+$/, '');
  }

  // ---------- images and fonts ----------
  function timeout(ms) {
    if (typeof AbortController === 'undefined') return {};
    var c = new AbortController(); setTimeout(function () { c.abort(); }, ms); return { signal: c.signal };
  }

  async function getBytes(url, ms) {
    var opt = timeout(ms || 30000);
    opt.credentials = url.indexOf(location.origin) === 0 ? 'include' : 'omit';
    var r = await fetch(url, opt);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return { type: (r.headers.get('content-type') || '').split(';')[0].trim().toLowerCase(), data: new Uint8Array(await r.arrayBuffer()) };
  }

  function sniff(d) {
    if (d[0] === 0x89 && d[1] === 0x50) return 'image/png';
    if (d[0] === 0xff && d[1] === 0xd8) return 'image/jpeg';
    if (d[0] === 0x47 && d[1] === 0x49 && d[2] === 0x46) return 'image/gif';
    var head = new TextDecoder().decode(d.slice(0, 300));
    if (/<svg[\s>]/.test(head)) return 'image/svg+xml';
    if (head.slice(0, 4) === 'RIFF' && head.slice(8, 12) === 'WEBP') return 'image/webp';
    return '';
  }

  async function toPng(source) {
    var bmp = source instanceof Blob ? await createImageBitmap(source) : source;
    var w = bmp.naturalWidth || bmp.width, h = bmp.naturalHeight || bmp.height;
    if (!w || !h) throw new Error('empty image');
    var cv = doc.createElement('canvas'); cv.width = w; cv.height = h;
    cv.getContext('2d').drawImage(bmp, 0, 0);
    var blob = await new Promise(function (res) { cv.toBlob(res, 'image/png'); });   // throws if tainted
    if (!blob) throw new Error('canvas export failed');
    return new Uint8Array(await blob.arrayBuffer());
  }

  async function loadImage(im) {
    for (var i = 0; i < im.urls.length; i++) {
      try {
        var got = await getBytes(im.urls[i]);
        var type = sniff(got.data);
        if (!type) continue;
        if (type === 'image/webp') { got.data = await toPng(new Blob([got.data])); type = 'image/png'; }
        return { type: type, data: got.data };
      } catch (e) { }
    }
    // last resort: the picture already shown on the page (works when not cross-origin)
    try {
      if (im.live && im.live.complete && im.live.naturalWidth > 4) return { type: 'image/png', data: await toPng(im.live) };
    } catch (e) { }
    return null;
  }

  async function fetchImages(book) {
    var done = 0;
    await Promise.all(book.images.map(async function (im) {
      var got = await loadImage(im);
      status('figures ' + (++done) + '/' + book.images.length + '...');
      if (got) {
        im.type = got.type; im.data = got.data;
        im.name = 'img/fig' + im.n + ({ 'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/svg+xml': '.svg' })[got.type];
        im.node.setAttribute('src', im.name);
      } else {
        var inFig = im.node.parentNode.localName === 'figure';
        var p = el(book, inFig ? 'p' : 'span'); p.setAttribute('class', 'missing');
        p.textContent = book.rtl ? '[התמונה לא הורדה]' : '[Figure not downloaded]';
        im.node.parentNode.replaceChild(p, im.node);
      }
    }));
  }

  async function fetchFonts() {
    var out = [];
    for (var i = 0; i < 2; i++) {
      var f = ['DavidLibre-Regular.ttf', 'DavidLibre-Bold.ttf'][i];
      try {
        var got = await getBytes(FONT_BASE + f, 15000);
        if (got.data.length > 10000 && got.data[0] === 0 && got.data[1] === 1) out.push({ name: f, data: got.data });
      } catch (e) { }
    }
    return out.length === 2 ? out : [];
  }

  // ---------- EPUB package ----------
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    var b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return (x + 256).toString(16).slice(1); }).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }

  function css(rtl, fonts) {
    var s = '';
    if (fonts.length) {
      s += '@font-face { font-family: "David Libre"; font-weight: normal; src: url("fonts/DavidLibre-Regular.ttf"); }\n' +
        '@font-face { font-family: "David Libre"; font-weight: bold; src: url("fonts/DavidLibre-Bold.ttf"); }\n';
    }
    s += 'body { font-family: ' + (fonts.length ? '"David Libre", ' : '') + 'serif; line-height: 1.5; text-align: ' + (rtl ? 'justify' : 'left') + '; }\n' +
      'h1, h2, h3 { text-align: center; font-weight: bold; }\n' +
      'h1 { font-size: 1.6em; }\nh2 { font-size: 1.35em; margin-top: 2em; }\nh3 { font-size: 1.1em; }\n' +
      'h4 { font-size: 1em; text-align: start; margin: 1.2em 0 0.4em; }\n' +
      'p { margin: 0; text-indent: 1.2em; }\n' +
      'h1 + p, h2 + p, h3 + p, h4 + p, li p, figure + p, table + p, blockquote p, aside p, p.byline, p.keywords { text-indent: 0; }\n' +
      'p.byline { text-align: center; margin: 0.5em 0 1.5em; }\n' +
      'p.keywords { margin-top: 0.8em; }\n' +
      (rtl ? 'em { font-style: normal; font-weight: bold; }\n' : '') +
      'blockquote { margin: 0.8em 1.5em; font-size: 0.95em; }\n' +
      '.box { border: 1px solid #555; background: #f2f2f2; padding: 0.4em 0.8em; margin: 1.2em 0; font-size: 0.95em; }\n' +
      'ol, ul { margin: 0.5em 0; padding-inline-start: 1.6em; list-style-position: outside; }\nli { text-align: start; }\n' +
      'ul.labelled { list-style: none; }\n' +
      'figure { margin: 1.2em 0; text-align: center; }\nfigure img { max-width: 100%; }\n' +
      'figcaption { font-size: 0.85em; text-align: start; margin-top: 0.3em; }\n' +
      'table { border-collapse: collapse; margin: 1em auto; font-size: 0.9em; }\n' +
      'td, th { border: 1px solid #555; padding: 0.3em 0.6em; text-align: start; vertical-align: top; }\n' +
      'caption { font-size: 0.9em; caption-side: top; margin-bottom: 0.3em; }\n' +
      'sup { font-size: 0.7em; line-height: 0; }\na.noteref { text-decoration: none; }\n' +
      'section.footnotes { font-size: 0.9em; margin-top: 2em; }\nsection.footnotes aside { margin: 0.4em 0; }\n' +
      'section.references p { text-indent: -1.2em; padding-inline-start: 1.2em; margin: 0.2em 0; }\n' +
      '.missing { text-align: center; font-style: italic; }\n';
    return s;
  }

  function navXhtml(art, book) {
    var hs = book.headings.filter(function (h) { return h.level >= 2 && h.level <= 4; });
    var x = '';
    var depth = 0;   // number of open <ol>
    hs.forEach(function (h, i) {
      var lvl = h.level - 1;  // 1..3
      if (i === 0) lvl = 1;
      if (lvl > depth + 1) lvl = depth + 1;   // no skipped levels
      while (depth > lvl) { x += '</li></ol>'; depth--; }
      if (depth === lvl) x += '</li>';
      while (depth < lvl) { x += '<ol>'; depth++; }
      x += '<li><a href="text.xhtml#' + h.id + '">' + esc(h.text) + '</a>';
    });
    while (depth > 0) { x += '</li></ol>'; depth--; }
    if (!hs.length) x = '<ol><li><a href="text.xhtml#title">' + esc(art.title) + '</a></li></ol>';
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n' +
      '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="' + art.lang + '" xml:lang="' + art.lang + '"' + (art.rtl ? ' dir="rtl"' : '') + '>\n' +
      '<head><meta charset="utf-8"/><title>' + esc(art.title) + '</title><link rel="stylesheet" type="text/css" href="style.css"/></head>\n' +
      '<body><nav epub:type="toc" id="toc"' + (art.rtl ? ' dir="rtl"' : '') + '><h1>' + (art.rtl ? 'תוכן' : 'Contents') + '</h1>' + x.replace(/<ol>/g, art.rtl ? '<ol dir="rtl">' : '<ol>') + '</nav>\n' +
      '<nav epub:type="landmarks" hidden="hidden"><ol><li><a epub:type="bodymatter" href="text.xhtml#title">' + esc(art.title) + '</a></li></ol></nav></body></html>\n';
  }

  function pack(art, book, fonts) {
    var text = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n' + new XMLSerializer().serializeToString(book.out) + '\n';
    var imgs = book.images.filter(function (im) { return im.data; });
    var id = 'urn:uuid:' + uuid();
    var modified = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
    var manifest = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n' +
      '<item id="text" href="text.xhtml" media-type="application/xhtml+xml"/>\n' +
      '<item id="css" href="style.css" media-type="text/css"/>\n';
    imgs.forEach(function (im, i) { manifest += '<item id="img' + (i + 1) + '" href="' + im.name + '" media-type="' + im.type + '"/>\n'; });
    fonts.forEach(function (f, i) { manifest += '<item id="font' + (i + 1) + '" href="fonts/' + f.name + '" media-type="font/ttf"/>\n'; });
    var opf = '<?xml version="1.0" encoding="UTF-8"?>\n' +
      '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="' + art.lang + '"' + (art.rtl ? ' dir="rtl"' : '') + '>\n' +
      '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n' +
      '<dc:identifier id="bookid">' + id + '</dc:identifier>\n' +
      '<dc:title>' + esc(libraryName(art)) + '</dc:title>\n' +
      (art.authors.length ? '<dc:creator>' + esc(art.authors.join(', ')) + '</dc:creator>\n' : '') +
      '<dc:language>' + art.lang + '</dc:language>\n' +
      '<meta property="dcterms:modified">' + modified + '</meta>\n' +
      '</metadata>\n<manifest>\n' + manifest + '</manifest>\n' +
      '<spine' + (art.rtl ? ' page-progression-direction="rtl"' : '') + '>\n<itemref idref="text"/>\n</spine>\n</package>\n';
    var container = '<?xml version="1.0" encoding="UTF-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n' +
      '<rootfiles><rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n</container>\n';
    var enc = new TextEncoder();
    var files = [
      { name: 'mimetype', data: enc.encode('application/epub+zip'), store: true },
      { name: 'META-INF/container.xml', data: enc.encode(container) },
      { name: 'EPUB/content.opf', data: enc.encode(opf) },
      { name: 'EPUB/nav.xhtml', data: enc.encode(navXhtml(art, book)) },
      { name: 'EPUB/text.xhtml', data: enc.encode(text) },
      { name: 'EPUB/style.css', data: enc.encode(css(art.rtl, fonts)) }
    ];
    imgs.forEach(function (im) { files.push({ name: 'EPUB/' + im.name, data: im.data, store: true }); });
    fonts.forEach(function (f) { files.push({ name: 'EPUB/fonts/' + f.name, data: f.data }); });
    return files;
  }

  // Library name, same rules as scripts/book_name.py: "Surname - Year - Short title"
  // (2 authors "A & B" / "A וB", 3+ "A et al." / "A ואחרים"; no year: left out).
  // Used for the file name and dc:title, because the Boox library shows dc:title.
  function pubYear() {
    var d = meta('citation_publication_date')[0] || meta('citation_date')[0] || meta('citation_online_date')[0] ||
      meta('article:published_time')[0] || meta('dc.date')[0] || meta('DC.date')[0] || '';
    var m = /(1[5-9]|20)\d\d/.exec(d);
    return m ? m[0] : '';
  }

  function libraryName(art) {
    var hebrew = /[\u0590-\u05ff]/.test(art.title + art.authors.join(' '));
    var names = art.authors.join(',').split(/,| and | & /).map(function (a) { return a.trim(); })
      .filter(Boolean).map(function (a) { return a.split(/\s+/).pop(); });
    var who = names.length === 1 ? names[0] : names.length === 2 ? (hebrew ? names[0] + ' \u05d5' + names[1] : names[0] + ' & ' + names[1])
      : names.length ? names[0] + (hebrew ? ' \u05d5\u05d0\u05d7\u05e8\u05d9\u05dd' : ' et al.') : '';
    var t = art.title;
    if (t.replace(/^:+|:+$/g, '').indexOf(':') >= 0) t = t.split(':')[0];
    t = t.replace(/[\\\/:*?"<>|\u05f4\u201c\u201d\u0000-\u001f]/g, '').replace(/\s+/g, ' ').replace(/^[\s.,\-\u2013\u2014']+|[\s.,\-\u2013\u2014']+$/g, '');
    if (t.length > 100) t = t.slice(0, 100).replace(/\s+\S*$/, '');
    return [who, art.year, t].filter(Boolean).join(' - ') || 'article';
  }


  // ---------- ZIP writer (stored or deflated) ----------
  var CRC = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })();
  function crc32(d) {
    var c = 0xffffffff;
    for (var i = 0; i < d.length; i++) c = CRC[(c ^ d[i]) & 255] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  async function deflate(d) {
    if (typeof CompressionStream === 'undefined') return null;
    try {
      var s = new Blob([d]).stream().pipeThrough(new CompressionStream('deflate-raw'));
      return new Uint8Array(await new Response(s).arrayBuffer());
    } catch (e) { return null; }
  }

  async function zip(files) {
    var now = new Date();
    var time = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
    var date = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
    var enc = new TextEncoder();
    var parts = [], central = [], offset = 0;
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      var name = enc.encode(f.name);
      var crc = crc32(f.data);
      var body = f.data, method = 0;
      if (!f.store) {
        var z = await deflate(f.data);
        if (z && z.length < f.data.length) { body = z; method = 8; }
      }
      var lh = new DataView(new ArrayBuffer(30));
      lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
      lh.setUint16(8, method, true); lh.setUint16(10, time, true); lh.setUint16(12, date, true);
      lh.setUint32(14, crc, true); lh.setUint32(18, body.length, true); lh.setUint32(22, f.data.length, true);
      lh.setUint16(26, name.length, true); lh.setUint16(28, 0, true);
      parts.push(new Uint8Array(lh.buffer), name, body);
      var ch = new DataView(new ArrayBuffer(46));
      ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true);
      ch.setUint16(10, method, true); ch.setUint16(12, time, true); ch.setUint16(14, date, true);
      ch.setUint32(16, crc, true); ch.setUint32(20, body.length, true); ch.setUint32(24, f.data.length, true);
      ch.setUint16(28, name.length, true); ch.setUint32(42, offset, true);
      central.push(new Uint8Array(ch.buffer), name);
      offset += 30 + name.length + body.length;
    }
    var csize = central.reduce(function (s, p) { return s + p.length; }, 0);
    var end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
    end.setUint32(12, csize, true); end.setUint32(16, offset, true);
    return new Blob(parts.concat(central, [new Uint8Array(end.buffer)]), { type: 'application/epub+zip' });
  }

  // runs last: the var tables above must be set first
  try {
    await run();
  } catch (e) {
    status('failed: ' + (e && e.message ? e.message : e), true);
    window.__epubMeError = String(e && e.stack || e);
  }
})();
