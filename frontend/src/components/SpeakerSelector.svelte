<script lang="ts">
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';

  export interface SpeakerOption {
    id?: string | number;
    uuid?: string;
    name?: string;
    display_name?: string | null;
    speaker_label?: string | null;
  }

  export let speakerList: SpeakerOption[] = [];
  export let selectedSpeakerId: string | number | null = null;
  export let fallbackLabel: string = 'Unknown speaker';
  export let disabled: boolean = false;
  export let includeCreateOption: boolean = true;

  const dispatch = createEventDispatcher();

  let isOpen = false;
  let searchTerm = '';
  let containerEl: HTMLElement | null = null;

  const handleDocumentClick = (event: MouseEvent) => {
    if (!containerEl) return;
    if (!containerEl.contains(event.target as Node)) {
      isOpen = false;
    }
  };

  onMount(() => {
    document.addEventListener('mousedown', handleDocumentClick);
  });

  onDestroy(() => {
    document.removeEventListener('mousedown', handleDocumentClick);
  });

  $: filteredSpeakers = speakerList
    .filter((speaker) => {
      if (!searchTerm.trim()) return true;
      const term = searchTerm.trim().toLowerCase();
      const baseLabel = (speaker.name || speaker.speaker_label || '').toLowerCase();
      const displayName = (speaker.display_name || '').toLowerCase();
      return baseLabel.includes(term) || displayName.includes(term);
    })
    .sort((a, b) => {
      // Preserve original numbering order (SPEAKER_XX)
      const getNumber = (name?: string) => {
        if (!name || !name.startsWith('SPEAKER_')) return 999;
        const num = parseInt(name.split('_')[1] || '0', 10);
        return isNaN(num) ? 999 : num;
      };
      return getNumber(a.name) - getNumber(b.name);
    });

  $: selectedSpeaker = findSpeaker(selectedSpeakerId);
  $: selectedLabel = selectedSpeaker ? formatSpeakerLabel(selectedSpeaker, true) : fallbackLabel;
  $: nextSpeakerCode = computeNextSpeakerCode(speakerList);

  function findSpeaker(id: string | number | null) {
    if (id === null || id === undefined) return null;
    const target = id.toString();
    return (
      speakerList.find((speaker) => {
        const candidateId =
          (speaker.id !== undefined ? speaker.id : speaker.uuid) ??
          speaker.name ??
          speaker.speaker_label;
        return candidateId?.toString() === target;
      }) || null
    );
  }

  function formatSpeakerLabel(speaker: SpeakerOption, compact = false) {
    const baseLabel = speaker.name || speaker.speaker_label || fallbackLabel;
    const displayName = (speaker.display_name || '').trim();
    if (!displayName || displayName.startsWith('SPEAKER_')) {
      return baseLabel;
    }
    return compact ? `${baseLabel} · ${displayName}` : `${baseLabel} — ${displayName}`;
  }

  function computeNextSpeakerCode(list: SpeakerOption[]): string {
    let max = 0;
    list.forEach((speaker) => {
      const name = speaker.name || speaker.speaker_label;
      if (!name || !name.startsWith('SPEAKER_')) return;
      const value = parseInt(name.split('_')[1] || '0', 10);
      if (!isNaN(value) && value > max) {
        max = value;
      }
    });
    const next = max + 1;
    return `SPEAKER_${next.toString().padStart(2, '0')}`;
  }

  function handleSelect(speaker: SpeakerOption) {
    const candidateId =
      (speaker.id !== undefined ? speaker.id : speaker.uuid) ??
      speaker.name ??
      speaker.speaker_label;

    selectedSpeakerId = candidateId ?? null;
    dispatch('change', { speakerId: selectedSpeakerId });
    searchTerm = '';
    isOpen = false;
  }

  function handleCreateNew() {
    dispatch('createNew', { suggestedName: nextSpeakerCode });
    isOpen = false;
  }
</script>

<div class="speaker-selector" bind:this={containerEl}>
  <button
    class="selector-trigger"
    type="button"
    disabled={disabled}
    on:click={() => (isOpen = !isOpen)}
    aria-haspopup="listbox"
    aria-expanded={isOpen}
  >
    <span class="label-text">{selectedLabel}</span>
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </button>

  {#if isOpen}
    <div class="selector-dropdown" role="listbox">
      <input
        class="selector-search"
        type="text"
        placeholder="Search speaker"
        bind:value={searchTerm}
        autofocus
      />

      {#if filteredSpeakers.length === 0}
        <div class="selector-empty">No matches found</div>
      {:else}
        <ul class="selector-list">
          {#each filteredSpeakers as speaker}
            <li>
              <button
                type="button"
                class:selected={selectedSpeakerId?.toString() ===
                  (
                    (speaker.id !== undefined ? speaker.id : speaker.uuid) ??
                    speaker.name ??
                    speaker.speaker_label ??
                    ''
                  ).toString()}
                on:click={() => handleSelect(speaker)}
              >
                <span class="option-primary">{formatSpeakerLabel(speaker)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}

      {#if includeCreateOption}
        <div class="selector-footer">
          <button type="button" class="create-button" on:click={handleCreateNew}>
            Create {nextSpeakerCode}
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .speaker-selector {
    position: relative;
    min-width: 180px;
  }

  .selector-trigger {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    border: 1px solid var(--border-color);
    background: var(--surface-color);
    cursor: pointer;
    font-weight: 600;
    font-size: 0.85rem;
  }

  .selector-trigger:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .selector-trigger svg {
    stroke: currentColor;
    stroke-width: 2;
    fill: none;
  }

  .selector-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    width: 280px;
    max-height: 360px;
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
    z-index: 20;
    display: flex;
    flex-direction: column;
  }

  .selector-search {
    border: none;
    border-bottom: 1px solid var(--border-color);
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    outline: none;
  }

  .selector-list {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 220px;
    overflow-y: auto;
  }

  .selector-list li button {
    width: 100%;
    text-align: left;
    padding: 0.5rem 0.75rem;
    border: none;
    background: transparent;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    cursor: pointer;
    font-size: 0.85rem;
  }

  .selector-list li button:hover,
  .selector-list li button.selected {
    background: rgba(59, 130, 246, 0.08);
  }

  .option-primary {
    font-weight: 600;
    color: var(--text-primary);
  }

  .selector-empty {
    padding: 0.75rem;
    font-size: 0.85rem;
    color: var(--text-secondary-color);
  }

  .selector-footer {
    border-top: 1px solid var(--border-color);
    padding: 0.5rem 0.75rem;
  }

  .create-button {
    width: 100%;
    border: none;
    background: #3b82f6;
    color: white;
    padding: 0.4rem 0.75rem;
    border-radius: 6px;
    font-size: 0.85rem;
    cursor: pointer;
  }

  .create-button:hover {
    background: #2563eb;
  }

  @media (max-width: 480px) {
    .selector-dropdown {
      width: 240px;
    }
  }
</style>

