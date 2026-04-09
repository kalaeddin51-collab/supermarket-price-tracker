"""
CLI management tool for the supermarket price tracker.

Usage:
  python manage.py init-db          — create database tables
  python manage.py search <query>   — search Woolworths for a product
  python manage.py scrape           — scrape all watched products (Phase 5)
"""
import asyncio
import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli():
    pass


@cli.command()
def init_db():
    """Create all database tables."""
    from app.database import init_db as _init_db
    _init_db()
    console.print("[green]Database initialised.[/green]")


@cli.command()
@click.argument("query")
@click.option("--store", default="woolworths", help="Store to search (woolworths, coles, harris_farm)")
@click.option("--limit", default=10, help="Number of results")
def search(query: str, store: str, limit: int):
    """Search for a product by name."""
    async def _run():
        if store == "woolworths":
            from app.scrapers.woolworths import WoolworthsScraper
            scraper = WoolworthsScraper()
        elif store == "coles":
            from app.scrapers.coles import ColesScraper
            scraper = ColesScraper()
        else:
            console.print(f"[yellow]Store '{store}' scraper not yet implemented.[/yellow]")
            return

        console.print(f"Searching [bold]{store}[/bold] for: [cyan]{query}[/cyan]")
        results = await scraper.search(query, limit=limit)
        await scraper.close()

        if not results:
            console.print("[red]No results found.[/red]")
            return

        table = Table(title=f"{store.title()} results for '{query}'")
        table.add_column("ID", style="dim")
        table.add_column("Name")
        table.add_column("Price", justify="right")
        table.add_column("Unit", style="dim")
        table.add_column("URL", style="blue")

        for r in results:
            price_str = f"${r.price:.2f}" if r.price is not None else "N/A"
            table.add_row(r.external_id, r.name, price_str, r.unit or "", r.url)

        console.print(table)

    asyncio.run(_run())


@cli.command()
@click.argument("external_id")
@click.option("--store", default="woolworths")
def fetch(external_id: str, store: str):
    """Fetch the current price for a single product by its store ID."""
    async def _run():
        if store == "woolworths":
            from app.scrapers.woolworths import WoolworthsScraper
            scraper = WoolworthsScraper()
            url = f"https://www.woolworths.com.au/shop/productdetails/{external_id}"
        elif store == "coles":
            from app.scrapers.coles import ColesScraper
            scraper = ColesScraper()
            url = f"https://www.coles.com.au/product/product-{external_id}"
        else:
            console.print(f"[yellow]Store '{store}' not yet implemented.[/yellow]")
            return

        result = await scraper.fetch_price(external_id, url)
        await scraper.close()

        if result.error:
            console.print(f"[red]Error: {result.error_message}[/red]")
            return

        console.print(f"\n[bold]{result.name}[/bold]")
        console.print(f"  Store   : {result.store}")
        console.print(f"  Price   : ${result.price:.2f}" if result.price else "  Price   : N/A")
        if result.was_price:
            console.print(f"  Was     : ${result.was_price:.2f}")
        console.print(f"  Special : {'Yes' if result.on_special else 'No'}")
        console.print(f"  In stock: {'Yes' if result.in_stock else 'No'}")
        console.print(f"  Unit    : {result.unit or 'N/A'}")

    asyncio.run(_run())


@cli.command()
def fetch_prices():
    """Scrape all watched products and run the alert evaluation engine."""
    from app.database import get_db
    from app.notifiers.alerts import evaluate_alerts

    async def _scrape_all(db):
        entries = []
        try:
            from app import models as m
            from app.scrapers.woolworths import WoolworthsScraper
            from app.scrapers.coles import ColesScraper
        except ImportError as e:
            console.print(f"[red]Import error: {e}[/red]")
            return

        wl_entries = db.query(m.WatchlistEntry).all()
        if not wl_entries:
            console.print("[yellow]No watchlist entries — nothing to scrape.[/yellow]")
            return

        ww = WoolworthsScraper()
        co = ColesScraper()
        scraped = 0

        for entry in wl_entries:
            product = entry.product
            store = str(product.store.value if hasattr(product.store, 'value') else product.store)
            try:
                if store == "woolworths":
                    result = await ww.fetch_price(product.external_id, product.url)
                elif store == "coles":
                    result = await co.fetch_price(product.external_id, product.url)
                else:
                    console.print(f"  [dim]Skipping {store} (scraper not yet built)[/dim]")
                    continue

                if result.error:
                    record = m.PriceRecord(product_id=product.id, scrape_error=True)
                else:
                    record = m.PriceRecord(
                        product_id=product.id,
                        price=result.price,
                        was_price=result.was_price,
                        in_stock=result.in_stock,
                        on_special=result.on_special,
                        scrape_error=False,
                    )
                db.add(record)
                scraped += 1
                price_str = f"${result.price:.2f}" if result.price else "N/A"
                console.print(f"  [green]✓[/green] {product.name[:50]} → {price_str}")
            except Exception as exc:
                console.print(f"  [red]✗[/red] {product.name[:50]}: {exc}")

        db.commit()
        await ww.close()
        await co.close()
        console.print(f"\n[bold green]Scraped {scraped} products.[/bold green]")

    db_gen = get_db()
    db = next(db_gen)
    try:
        asyncio.run(_scrape_all(db))
        console.print("\n[cyan]Running alert evaluation...[/cyan]")
        events = evaluate_alerts(db)
        if events:
            console.print(f"[bold yellow]{len(events)} alert(s) fired and notifications sent.[/bold yellow]")
        else:
            console.print("[dim]No new alerts.[/dim]")
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    cli()
