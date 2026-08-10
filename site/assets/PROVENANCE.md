# Academy design provenance

Academy Preview 0.2 adapts platform-neutral design primitives from the local
`codeArbiter` checkout at commit `9ce7faceccaae819730a3534fdc6aa0992ab04bc`.
It does not import Astro or Starlight code at build or runtime.

Reviewed source identities:

- `site/src/styles/design-system.css`: `1b4faf0a6729ba71a74063f4b6a77cc1214f2af158ff156bab618cd5b58c8044`
- `site/src/assets/favicon.svg`: `49e2ee37ad5d86b700a4d10f74bd9586afe5dcd8dfbe8823a23a9c0f0088b018`
- `site/src/assets/gate-mark.svg`: `ff6446d218cc0367141765bafd2840ed0ea703773f5d05c7ed36a9cb14ba6330`
- `site/src/assets/hero-gates.webp`: `95893d3b7dac3a84cb9641145509b10b0290587d5b9da456b27f85dd649b43be`
- `site/src/assets/logo.svg`: `4553873806ba21a9de652105d3330626b1301eefe50eb7d61a1f3f7efacb768a`
- `site/src/components/ArbiterIcon.astro`: `8bfc315085c0438eaf953cbffb0f5b898317cc5ca644f82b335ebdfb42d5fbb5`
- `site/src/components/PageContext.astro`: `02e646dc5146f8a3275178e01d5a0b88dbee12286bb627ff1d4d7bc9aa547446`
- `site/src/components/ConceptNavigator.astro`: `cc6e791a050a70735cc2d6ddb56f8b88bdb12e722205a91b64f900e376ed346b`
- `site/src/components/SidebarSublist.astro`: `7400e96821e3689518dca1ff8a3fbaddf4f6d92b6240963e4f8d5e280aae518e`

The Manrope and JetBrains Mono bytes and licenses were already present in this
repository. The Academy publisher copies only the listed local runtime assets;
this provenance record remains a source review artifact and is not emitted.
