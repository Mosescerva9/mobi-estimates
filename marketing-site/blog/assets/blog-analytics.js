// Draft-only blog analytics event definitions. No network calls are made in preview.
(function(){
  const defs = {
    article_view: 'Page view for blog article or archive',
    scroll_depth: '25/50/75/100 percent scroll milestones',
    toc_click: 'Table-of-contents anchor click',
    internal_link_click: 'Internal article link click',
    sample_cta_click: 'Sample-estimate CTA click',
    upload_plans_cta_click: 'Upload-plans CTA click',
    related_click: 'Related article click',
    source_video_click: 'Source video click',
    archive_click: 'Blog archive card click-through'
  };
  window.MOBI_BLOG_ANALYTICS_DEFINITIONS = defs;
  if (!window.MOBI_BLOG_PREVIEW) return;
  document.addEventListener('click', function(e){
    const a=e.target.closest('a'); if(!a) return;
    const event=a.dataset.analytics || (a.href && a.href.includes('youtube.com') ? 'source_video_click' : (a.host===location.host || a.getAttribute('href')?.startsWith('..') ? 'internal_link_click' : null));
    if(event) console.info('[Mobi blog analytics preview]', event, a.href);
  });
})();
