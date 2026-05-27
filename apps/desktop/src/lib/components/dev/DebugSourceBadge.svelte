<script lang="ts">
  import type { DataSourceInfo } from '../../contracts/isotope';

  let { source } = $props<{ source: DataSourceInfo }>();
</script>

<span class="border border-isotope-line bg-white/60 px-1.5 py-0.5 text-[10px] font-medium uppercase text-isotope-muted">
  {source.kind}
</span>
