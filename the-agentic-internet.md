---
description: Agents are a new kind of visitor. They don&#39;t render CSS or click ads, but they have a paying human on the other end. Block them and you block your customer. We&#39;re building the open tools and protocols so publishers and agents can cooperate and not collide.
title: Building an open Agentic Internet: readable, discoverable, callable, and payable
image: https://blog.cloudflare.com/_emdash/api/media/file/01KZA0FMKFRS1HHGE59X56THGG.png
---

[Skip to content](#main-content)

![](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZA0FMHPRQW9N737YVV9WYRZ.png&w=1999&h=1125&f=webp&fit=cover&position=center)![]()

Our data shows that a lot of traffic from well-behaved bots is [re-fetching pages that have not changed](https://blog.cloudflare.com/making-ai-search-smarter/). Billions of requests. An enormous amount of machine effort, attached to no outcome at all. That's the signature of a web built for humans being visited by something else.

Agents are here - not as a new kind of software, but as a new kind of visitor to the web.

The web reshaped around this new visitor is what we call the Agentic Internet. We see its future as readable, discoverable, callable, and payable. To realize that future, it needs its own tools and protocols.

Cloudflare's developer platform gave agents a place to run, and the first tools to build them. What's missing are the ones that let agents and domain owners cooperate instead of collide — on the open Internet, not just inside a single platform.

Every browser has always identified itself to the web with a header called User-Agent. The name only made sense once you realized the browser was acting on your behalf. Now a user agent is truly a user's agent: a program that fetches the web on a person's behalf. Today its most mature form is the coding agent that reads and writes code, pulls the docs it needs, and never sees the pages it reads.

An agent doesn't render your CSS, see your hero image, or click your ads. But it has a paying human on the other end. Every request now costs someone money and carries a purpose. Block it and you block your customer. Treat it like a scraper and you lose them.

Every agent runs because someone — a person or a business — is paying for what it does. Most people don't spend tokens for the sake of it. This version of the Internet, one with an outcome and a bill on the other end of every request, is going to look nothing like the one we have now.

The web was not built for this, and neither were your analytics. Nor, in most cases, was your business model. How agents read, discover, call, and pay is going to decide whether the Internet stays open or gets closed. In one version of the future, a handful of stacks own discovery, identity, and payments, and everyone else routes through them. In another, the Internet stays open: primitives built on standards anyone can implement, running on rails that are neutral because the code is public.

Cloudflare believes in the open Internet, and we're in a position to help build the future where it thrives.

![]()![The shaded portion is bots re-fetching content that hasn't changed since the last crawl. Machine effort a domain owner paid to serve and an agent paid to make, with no outcome for either side. ](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZA0FN16ARXEBX3WSM9XNTM9.png&w=715&h=377&f=webp&fit=cover&position=center)

The shaded portion is bots re-fetching content that hasn't changed since the last crawl. Machine effort a domain owner paid to serve and an agent paid to make, with no outcome for either side. 

The specifications we build on are open standards that anyone can implement — x402, MCP, Web Bot Auth, PACT. Domain owners choose their own identity providers, their own payment processors, their own agent partners. Cloudflare is one option, not the whole stack. We are Customer Zero of the same rails our customers use, with no privileged path or early-access API that only we can reach. This is the job we've done for the human web for fifteen years, and it's the job we intend to do for the Agentic Internet.

The engineering is not what humans on the Agentic Internet will notice. They're picking up a new medium, and they'll judge it the way they judged the web: on whether it's better. Whether finding and booking a table takes one exchange instead of nine. Whether they know who they're dealing with. Whether paying feels safe.

## Our philosophy: A readable, discoverable, callable, and payable Agentic Internet

This starts with identity. [Web Bot Auth](https://blog.cloudflare.com/web-bot-auth/) lets a bot cryptographically identify itself to any site it visits, so publishers can decide who they welcome and who they don't. No more guessing and no more spoofed user agents. Many sites already know the human behind a request from login, in-app behavior, or purchase history. That site can issue [Private Access Control Tokens ](https://cloudflare.net/news/news-details/2026/Cloudflare-Collaborates-With-Leading-Browsers-to-Develop-a-Privacy-First-Protocol-For-the-Global-Internet/default.aspx)(PACT). Announced with Mozilla, Google, Microsoft, and Shopify, PACT lets sites vouch anonymously, so the agent can present the token elsewhere. Legitimate agents get in with less friction.

We can then make it easier for an agent to do its job. [Markdown for Agents](https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/) lets agents read websites with fewer tokens and less bandwidth. [WebMCP](https://blog.cloudflare.com/webmcp/) gives them a native way to interact on your behalf. Standards like [x402](https://x402.org/) let them pay merchants directly.

**Readable** is straightforward. Can AI agents read content in a way that is native to them and plays to their strengths? The less bandwidth and fewer tokens an agent burns, the better. Every HTML tag rendered for a human that never looks at it is not only a waste of compute but also a pollution of the context window the agent then has to pay to ignore. [Markdown for Agents](https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/) addresses this from the server side.

On the client side, we approached building a browser with agents in mind as first-class citizens. [Kitesurf](http://blog.cloudflare.com/kitesurf) is our new browser lean enough to run on Workers, spun up per request and thrown away after. It delivers content and features that agents need without any of the bloat from human-oriented features in traditional browsers.

**Discoverable** is where every economic moment on the Agentic Internet begins. Before an agent can read a resource, call a tool, or pay for a transaction, it has to know the resource is there. Search is one half of the story, as agents need to find what they need through interfaces built for them, not through a keyword box designed for a human who types slowly and skims. [AI Search](https://developers.cloudflare.com/ai-search/) is available today, so any public site can be made searchable by agents.

Being discovered is the other part. Content creators and API owners need to know how visible they are to agents. [Agent Engine Optimization (AEO) ](http://blog.cloudflare.com/aeo)measures brand visibility across the models and agents that matter. If you are not measurably visible to the agents your customers use, then you are effectively offline for them. 

**Callable** is where the agents start doing things: booking a table, renewing a subscription, pulling a report. On the human web these all look different, because they were built for humans clicking through user interfaces. An agent trying to add an item to a to-do list has to parse the HTML, guess which button is “Add”, synthesize a click, and hope the DOM didn’t change since it last looked.

[WebMCP](https://blog.cloudflare.com/webmcp/) lets a site expose its actions directly to agents through the browser:

```
document.modelContext.registerTool({
  name: "add-todo",
  description: "Add a new item to the user's active todo list",
  inputSchema: {
    type: "object",
    properties: {
      text: { type: "string", description: "The todo item text" }
    },
    required: ["text"]
  },
  async execute({ text }) {
    await addTodoItemToCollection(text);
    return { content: [{ type: "text", text: `Added: "${text}"` }] };
  }
});
```

The tool “contract” becomes explicit. No HTML parsing, no guessing at form fields. As the tools run inside the page, they reuse the user’s existing session and state. [Code Mode](https://blog.cloudflare.com/code-mode/) goes one step further. Agents think in code, and calling tools by writing code is faster and more accurate than prose. As agents are calling endpoints rather than scraping webpages, there is a clear signal back to the content owner of what content is actually being used. 

**Payable** is where we believe the Agentic Internet is going. Every economic transaction eventually needs a way to pay. Ad-based models are breaking. Seat-based models do not work when the user is a program. The publishers we all rely on cannot fund themselves on pageviews that never happen and browsers that do not render their ads. 

A recipe site that never turned a profit using ads can charge a fraction of a cent per fetch and be profitable at the scale of the Agentic Internet. A local paper can license articles at read time without a licensing deal or login. On the other side, the agent shows up with a wallet and a budget the human set once. 

Every paid interaction leaves a receipt. The publisher can prove which agent fetched which page. The agent can prove it paid for what it used. [Wallets](https://blog.cloudflare.com/wallets/) allow agents to easily pay for content and APIs. [Monetization Gateway](https://blog.cloudflare.com/monetization-gateway/) lets domain owners set up payments from agents in a few clicks.

Cloudflare sits in the middle of all of this by design. We already sit between billions of humans and the sites they visit, protecting them, speeding them up, keeping them online. Agents change the traffic but not the shape of that job — we're the neutral, high-performance layer that publishers, merchants, agent builders, and end users can all trust to be on their side, not competing with them. 

We want to give domain owners the tools to empower the kinds of AI agents that they want to support and [block the ones that they don’t](https://blog.cloudflare.com/cloudflare-ai-audit-control-ai-content-crawlers/). A developer tool likely wants to become [agent-ready](http://blog.cloudflare.com/aeo) to encourage AI agents to discover, recommend, and pay them. A publisher may want to block extractive AI agents (which consume resources without giving anything back) but allow AI agents that license their content or compensate them. A nonprofit data provider may want to block bots or humans who exceed their rate limits, but allow them to pay to get unblocked and use those funds to cover the excess resource consumption.

## Bots are dead, long live bots

The distinction between a [bot and a human isn’t so simple anymore](https://blog.cloudflare.com/past-bots-and-humans/). It’s not as straightforward as bots are bad and humans are good, or bots wasting resources that humans should instead consume. This is the old way of thinking that is outdated in the world of agents.

We see agents as a new type of actor. Their actions can be desirable, say, by reading content in a way that preserves resources, interacting with websites in the way that the domain owners specify, and paying for what they use. Or their actions can be undesirable, for example, by scraping millions of pages without compensation, attempting to circumvent blocks, or ignoring [robots.txt](https://www.cloudflare.com/learning/bots/what-is-robots-txt/). We believe that many of the undesirable actions will diminish, and even convert to desirable actions, if humans and bots are given the right tools.

## Closing the revenue gap

Cloudflare has spent years detecting bots, allowing domain owners to take control of whether bots can access them. What's been missing is the other half: how agents interact with those sites once they're let in. That's what this suite of agentic tools is for: making the web readable, discoverable, callable, payable. These four primitives are all built on open standards, so no single company owns the rails. 

An open Agentic Internet needs diversity on both sides. Not just diverse publishers and content creators but also diverse agents. If the demand side converges, it doesn’t matter how open the supply side is. The Internet will still be a walled garden.

We are building this open alternative. Join us by getting your site [agent ready with our new dashboard](http://blog.cloudflare.com/aeo), and sign up to receive news on our Answer Engine Optimization product. If you run a site or an agent, you can experiment with all of the Internet's new technologies using our [AI Playground](https://playground.ai.cloudflare.com/).

Discuss Online

## Related tags

[Agents](https://blog.cloudflare.com/tag/agents/)[Agents Week](https://blog.cloudflare.com/tag/agents-week/)[AI](https://blog.cloudflare.com/tag/ai/)[Developer Platform](https://blog.cloudflare.com/tag/developer-platform/)[Developers](https://blog.cloudflare.com/tag/developers/)[MCP](https://blog.cloudflare.com/tag/mcp/)

Follow on Social Media

* ![Cloudflare](https://blog.cloudflare.com/images/placeholder__cloudflare.png)Cloudflare
* ![Jack Galilee](https://blog.cloudflare.com/_image?href=https%3A%2F%2Fblog.cloudflare.com%2F_emdash%2Fapi%2Fmedia%2Ffile%2F01KZA3MX64PMX25X6GHJWTCKYT.jpg&w=64&h=64&f=webp&fit=cover&position=center)[Jack Galilee](https://blog.cloudflare.com/author/jack-galilee/)

## Subscribe to receive notifications of new posts

Email address

We’ll never share your email address.

Subscribe

Thanks for subscribing! Check your inbox to confirm.

Search is temporarily unavailable.

[Login opens in a new tab](https://dash.cloudflare.com/login)[Dashboard opens in a new tab](https://dash.cloudflare.com)[Contact Sales opens in a new tab](https://www.cloudflare.com/resource/contact-enterprise-sales/)[Start Building opens in a new tab](https://dash.cloudflare.com/sign-up)

[ opens in a new tab](https://x.com/cloudflare)[ opens in a new tab](https://www.linkedin.com/company/cloudflare-inc-)[ opens in a new tab](https://blog.cloudflare.com/rss/)

All Categories

* [AI](https://blog.cloudflare.com/tag/ai/)
* [Developers](https://blog.cloudflare.com/tag/developers/)
* [Radar](https://blog.cloudflare.com/tag/cloudflare-radar/)
* [Product News](https://blog.cloudflare.com/tag/product-news/)
* [Security](https://blog.cloudflare.com/tag/security/)
* [Policy & Legal](https://blog.cloudflare.com/tag/policy/)
* [Zero Trust](https://blog.cloudflare.com/tag/zero-trust/)
* [Speed & Reliability](https://blog.cloudflare.com/tag/speed-and-reliability/)
* [Life at Cloudflare](https://blog.cloudflare.com/tag/life-at-cloudflare/)
* [Partners](https://blog.cloudflare.com/tag/partners/)

English

* This Post is Available in
* [Español](https://blog.cloudflare.com/es-es/the-agentic-internet/)
* [Español (Latinoamérica)](https://blog.cloudflare.com/es-la/the-agentic-internet/)
* [Français](https://blog.cloudflare.com/fr-fr/the-agentic-internet/)
* [Italiano](https://blog.cloudflare.com/it-it/the-agentic-internet/)
* [日本語](https://blog.cloudflare.com/ja-jp/the-agentic-internet/)
* [한국어](https://blog.cloudflare.com/ko-kr/the-agentic-internet/)
* [繁體中文](https://blog.cloudflare.com/zh-tw/the-agentic-internet/)
* [简体中文](https://blog.cloudflare.com/zh-cn/the-agentic-internet/)
* Switch Site Language
* [English](https://blog.cloudflare.com/)
* [Deutsch](https://blog.cloudflare.com/de-de/)
* [Español](https://blog.cloudflare.com/es-es/)
* [Español (Latinoamérica)](https://blog.cloudflare.com/es-la/)
* [Français](https://blog.cloudflare.com/fr-fr/)
* [Italiano](https://blog.cloudflare.com/it-it/)
* [日本語](https://blog.cloudflare.com/ja-jp/)
* [한국어](https://blog.cloudflare.com/ko-kr/)
* [繁體中文](https://blog.cloudflare.com/zh-tw/)
* [简体中文](https://blog.cloudflare.com/zh-cn/)
* [Português](https://blog.cloudflare.com/pt-br/)
* [Русский](https://blog.cloudflare.com/ru-ru/)
* [Bahasa Indonesia](https://blog.cloudflare.com/id-id/)
* [ภาษาไทย](https://blog.cloudflare.com/th-th/)
* [Tiếng Việt](https://blog.cloudflare.com/vi-vn/)
* [Polski](https://blog.cloudflare.com/pl-pl/)
* [العربية](https://blog.cloudflare.com/ar-ar/)
* [עברית](https://blog.cloudflare.com/he-il/)
* [Svenska](https://blog.cloudflare.com/sv-se/)
* [Nederlands](https://blog.cloudflare.com/nl-nl/)
* [Türkçe](https://blog.cloudflare.com/tr-tr/)

LightDark

```json
{"@context":"https://schema.org","@type":"BlogPosting","headline":"Building an open Agentic Internet: readable, discoverable, callable, and payable","description":"Agents are a new kind of visitor. They don't render CSS or click ads, but they have a paying human on the other end. Block them and you block your customer. We're building the open tools and protocols so publishers and agents can cooperate and not collide.","image":"https://blog.cloudflare.com/_emdash/api/media/file/01KZA0FMKFRS1HHGE59X56THGG.png","url":"https://blog.cloudflare.com/the-agentic-internet/","datePublished":"2026-08-06T13:00:00.000Z","dateModified":"2026-08-10T13:09:45.591Z","publisher":{"@type":"Organization","name":"Cloudflare Blog"},"mainEntityOfPage":{"@type":"WebPage","@id":"https://blog.cloudflare.com/the-agentic-internet/"}}
```
