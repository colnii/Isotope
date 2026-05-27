<script lang="ts">
  let { title, subtitle, body } = $props<{
    title: string;
    subtitle: string;
    body: string;
  }>();
</script>

<section class="min-w-0 px-8 py-6" aria-label="Conversation workspace">
  <div class="text-xs uppercase text-isotope-muted">{subtitle}</div>
  <h1 class="mt-2 max-w-3xl text-2xl font-semibold text-isotope-text">{title}</h1>
  <div class="mt-6 max-w-3xl border-l-2 border-isotope-line pl-4 text-sm leading-6 text-isotope-muted">
    {body}
  </div>
</section>
