<script lang="ts">
  import type { DataSourceInfo } from '../../contracts/isotope';
  import { dataSourceKindLabel } from '../../view/labels';

  let { source } = $props<{ source: DataSourceInfo }>();
</script>

<span class="border border-isotope-line bg-white/80 px-1.5 py-0.5 text-[11px] font-medium text-isotope-muted">
  {dataSourceKindLabel(source.kind)}
</span>
