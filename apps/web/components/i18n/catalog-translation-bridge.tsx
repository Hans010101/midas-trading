'use client'

import { useLocale } from 'next-intl'
import { useEffect, useMemo, useRef } from 'react'

import type { Locale } from '@/i18n/routing'
import academyInteractiveEn from '@/content/academy/interactive-ui.en.json'
import academyInteractiveZh from '@/content/academy/interactive-ui.zh.json'
import {
  buildTranslationCatalog,
  translateCatalogText,
} from '@/lib/i18n/catalog'
import enMessages from '@/messages/en.json'
import zhMessages from '@/messages/zh.json'

const ATTRIBUTES = ['aria-label', 'alt', 'placeholder', 'title'] as const
const SKIP_SELECTOR =
  '[data-i18n-skip],script,style,noscript,textarea,code,pre,[contenteditable="true"]'

type TextState = {
  source: string
  lastApplied: string
}

type AttributeState = {
  source: string
  lastApplied: string
}

const catalog = buildTranslationCatalog(
  { ...zhMessages, academyInteractive: academyInteractiveZh },
  { ...enMessages, academyInteractive: academyInteractiveEn },
)

function shouldSkip(node: Node): boolean {
  const parent = node instanceof Element ? node : node.parentElement
  return parent?.closest(SKIP_SELECTOR) !== null
}

export function CatalogTranslationBridge() {
  const locale = useLocale() as Locale
  const textStates = useRef(new WeakMap<Text, TextState>())
  const attributeStates = useRef(
    new WeakMap<Element, Map<string, AttributeState>>(),
  )
  const activeLocale = useMemo(() => locale, [locale])

  useEffect(() => {
    const translateText = (node: Text) => {
      if (shouldSkip(node)) return
      const current = node.nodeValue ?? ''
      let state = textStates.current.get(node)
      if (!state) {
        state = { source: current, lastApplied: current }
        textStates.current.set(node, state)
      } else if (current !== state.lastApplied) {
        state.source = current
      }
      const desired = translateCatalogText(
        state.source,
        activeLocale,
        catalog,
      )
      state.lastApplied = desired
      if (current !== desired) node.nodeValue = desired
    }

    const translateAttributes = (element: Element) => {
      if (shouldSkip(element)) return
      let states = attributeStates.current.get(element)
      if (!states) {
        states = new Map()
        attributeStates.current.set(element, states)
      }
      for (const name of ATTRIBUTES) {
        const current = element.getAttribute(name)
        if (current === null) continue
        let state = states.get(name)
        if (!state) {
          state = { source: current, lastApplied: current }
          states.set(name, state)
        } else if (current !== state.lastApplied) {
          state.source = current
        }
        const desired = translateCatalogText(
          state.source,
          activeLocale,
          catalog,
        )
        state.lastApplied = desired
        if (current !== desired) element.setAttribute(name, desired)
      }
    }

    const translateTree = (root: Node) => {
      if (root instanceof Text) {
        translateText(root)
        return
      }
      if (!(root instanceof Element) || shouldSkip(root)) return
      translateAttributes(root)
      const walker = document.createTreeWalker(
        root,
        NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
      )
      let current: Node | null = walker.nextNode()
      while (current) {
        if (current instanceof Text) translateText(current)
        else if (current instanceof Element) translateAttributes(current)
        current = walker.nextNode()
      }
    }

    translateTree(document.body)
    document.documentElement.dataset.localeReady = activeLocale

    const pending = new Set<Node>()
    let scheduled = false
    const flush = () => {
      scheduled = false
      for (const node of pending) translateTree(node)
      pending.clear()
    }
    const schedule = (node: Node) => {
      pending.add(node)
      if (!scheduled) {
        scheduled = true
        queueMicrotask(flush)
      }
    }

    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'childList') {
          for (const node of record.addedNodes) schedule(node)
        } else {
          schedule(record.target)
        }
      }
    })
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: [...ATTRIBUTES],
      characterData: true,
      childList: true,
      subtree: true,
    })
    return () => observer.disconnect()
  }, [activeLocale])

  return null
}
