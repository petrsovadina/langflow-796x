import { Disclosure } from "@headlessui/react";
import { DisclosureComponentType } from "../../../../types/components";
import { ChevronRight } from "lucide-react";

export default function DisclosureComponent({
  button: { title, Icon, buttons = [] },
  children,
  openDisc,
}: DisclosureComponentType) {
  return (
    <Disclosure as="div" key={title}>
      {({ open }) => (
        <>
          <div>
            <Disclosure.Button className="select-none bg-muted w-full flex justify-between items-center -mt-px px-3 py-2 border-y border-y-input">
              <div className="flex gap-4">
                <Icon strokeWidth={1.5} size={22} className="text-primary " />
                <span className="flex items-center text-sm text-primary">
                  {title}
                </span>
              </div>
              <div className="flex gap-2">
                {buttons.map((x, index) => (
                  <button key={index} onClick={x.onClick}>
                    {x.Icon}
                  </button>
                ))}
                <div>
                  <ChevronRight
                    className={`${
                      open || openDisc ? "rotate-90 transform" : ""
                    } h-4 w-4 text-foreground`}
                  />
                </div>
              </div>
            </Disclosure.Button>
          </div>
          <Disclosure.Panel as="div" className="-mt-px" static={openDisc}>
            {children}
          </Disclosure.Panel>
        </>
      )}
    </Disclosure>
  );
}
